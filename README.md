# 企业 OA 报备助手

员工报备前查制度、查审批链的双服务助手。业务数据走确定性规则引擎，制度问答走检索增强（RAG）+ 两层引用核验 + 结构化拒答。两层解耦，问答层出问题不影响 OA 业务查询。

检索与索引为自研实现，未使用 LangChain / LlamaIndex。

## 三层结构

`oa/` — 确定性业务层。金额以整数分存 SQLite，对外用 Decimal 换算并返回字符串，避免 float 精度问题。入参强校验，查询全部参数化。审批结论可追溯到规则编号与版本（PUR-001/002/003）。

`rag/` — 检索层。制度语料按「第 X 条」切分（保留条款下的子项），向量化后存 npz，余弦排序取 Top-5。索引文件带资料指纹，语料或模型一变更，检索前的校验就会拦住过期索引。

`assistant/` — 问答层。`/ask` 先由模型选意图，再分发：制度问答走 RAG，预算 / 审批链 / 供应商查询走 OA 工具调用。

制度问答的每条结论要过两道关：先由程序比对引文与检索原文**逐字一致**，再让模型复核语义是否真的支持结论、有无漏掉会改变结果的适用条件。两层都通过才渲染带编号引用的回答（制度名 / 版本 / 条号 / 来源文件 / 适用范围）。

工具调用则不信任任何一方。参数必须能在问题原文里找到（`source_value` 逐字校验），区间金额、多金额、外币一律要求澄清而不是猜；OA 返回的数据还要过一致性校验（例如剩余预算必须等于总额减已用），最后**确定性渲染，不经 LLM 改写**。

一个刻意的取舍：**金额不交给模型算**。审批档位（5000 / 20000 两个分界点）全部由代码判定，模型只负责理解问题和组织语言。这样审批结论可以追溯到规则编号，也不会出现「模型把 8000 算成 80000」这类事故。

## 环境配置

复制 `.env.example` 为 `.env`，填入阿里云百炼密钥。四个变量：`DASHSCOPE_API_KEY`、`DASHSCOPE_BASE_URL`、`CHAT_MODEL`、`EMBEDDING_MODEL`。`.env` 已被 `.gitignore` 排除。索引与评测报告生成在 `data/index/`，同样不入仓。

⚠️ **注意 embedding 模型要和你建索引时用的一致。** `.env.example` 里写的是 `text-embedding-v3`，我本地实际用的是 `text-embedding-v4`（1024 维）。如果换了模型而没重建索引，`search()` 会直接抛 `RuntimeError` 提示重建 —— 这是索引指纹在起作用，属于预期行为。

## 本地启动

先激活虚拟环境，以下命令均在项目根目录执行。

```powershell
# 1. 初始化 OA 数据（只补缺失记录，不覆盖已有数据）
python -m oa.db

# 2. OA 后端（8001）
python -m uvicorn oa.main:app --reload --host 127.0.0.1 --port 8001

# 3. 建索引（需先配好 .env）
python -m rag.build_index

# 4. 助手服务（8000），另开终端
python -m uvicorn assistant.main:app --reload --host 127.0.0.1 --port 8000
```

验收脚本：

| 脚本 | 覆盖范围 | 是否调用模型 |
|---|---|---|
| `check_day2.py` | OA 数据层 | 否 |
| `check_day3.py` | 检索层离线自检 | 否 |
| `check_day4.py` | 问答层（mock 模型） | 否 |
| `check_day5.py` | 工具调用参数与渲染（mock） | 否 |
| `check_day5_http.py` | 工具调用链路（模拟 HTTP） | 否 |
| `rag/evaluate.py` | 检索质量 Hit@1 / Hit@5 | 是 |
| `scripts/evaluate_answers.py` | 问答用例端到端 | 是 |
| `scripts/evaluate_tools.py` | 工具调用端到端 | 是 |

`check_day3.py` 的预期语料规模是命令行参数，**默认值仍是旧的 10 份 / 30 条**，当前语料已扩到 50 份 / 150 条，所以要带参数跑：

```powershell
python .\check_day3.py --expected-docs 50 --expected-chunks 150
```

## 部署（Docker Compose）

三服务编排，`nginx` 是唯一对外入口，只绑 `127.0.0.1:8081`：

| 服务 | 作用 | 端口 |
|---|---|---|
| `oa` | FastAPI 模拟 OA 后端 | 8001（容器内） |
| `assistant` | 问答与工具调用 | 8000（容器内） |
| `nginx` | 反向代理 | 宿主机 `127.0.0.1:8081` |

仓库根目录备齐 `.env` 与本地已构建的 `data/index/` 后：

```bash
docker compose up -d --build
```

几个刻意的设计：

- **健康检查分层**：`oa` 的探针打真实数据库接口 `/suppliers`，不是存活探针；`assistant` 用 `depends_on: condition: service_healthy` 等 `oa` 健康后才启动。但 `assistant` 自己的探针只打 `/health`，**仅证明进程活着，不证明密钥和索引可用** —— 这点在 `compose.yaml` 里写了注释，避免误判。
- **挂载不自动创建目录**：`data/policies` 和 `data/index` 以只读方式挂进 `assistant`，且 `create_host_path: false`。宿主机路径不存在时直接报错，而不是静默挂一个空目录进去 —— 空索引会让检索悄悄返回空结果，比启动失败更难查。
- **密钥纪律**：四个变量都是 `${VAR:?...}` 引用式，缺失时 compose 直接报错。配置文件里不写明文密钥，真实值只存在于本地 `.env`。
- 镜像基于 `python:3.12-slim`，以非 root 用户（uid 10001）运行；日志轮转上限 10m × 3；OA 的 SQLite 存命名卷 `oa_data` 持久化。

`deploy/` 下除了 `container_start.py`（统一容器入口）、`check_environment.py`（环境检查）、`compose.fault.yaml`（故障注入覆盖）、`persistence_probe.py`（持久化探针），还有 `acceptance.py`、`smoke.py`、`restore_check.py`、`backup.sh`、`check_runtime.py`、`render_config.py` 等运维脚本，以及 `deploy/nginx/` 下的多套反代配置模板和 `deploy/web/` 的静态页。

## 评测结果

以下是真实密钥跑出来的落盘数字，报告在 `data/index/`。

### 检索质量

`python -m rag.evaluate`，10 题开发用小样本（非独立测试集）：

- **Hit@1 = 9/10，Hit@5 = 10/10**

唯一未命中 Top-1 的是「采购金额为 8000 元时需要经过哪些人审批？」。排第一的是 `purchase_approval:demo-v1:第三条`（20000 元档，需总经理审批），正确的第二条排第二。

原因是 embedding 检索**不会做数值区间推理** —— 「8000 元」和三个档位条款在语义空间里距离都差不多近，排不出谁对。这也是为什么金额判定交给代码规则引擎而不是交给检索。当前架构下这题会先被路由到 `get_approval_chain` 工具，不依赖检索排序，所以不影响答案正确性；但它说明**任何依赖「按金额选条款」的检索场景都不可靠**。

### 问答用例

`python -m scripts.evaluate_answers --stage base`，14 道基础题。`data/day4_cases.json` 共 18 题（base 14 + expanded 4）。

⚠️ 现存的 `day4_base_report.json`（13/14 状态匹配）是 **Day 4 阶段的旧快照，不能代表当前状态**：当时还没有意图路由，报告里「研发部还剩多少预算」的回答是「尚未接通 OA 工具」。Day 5 接入路由后这类问题已能正常调用工具。要看当前表现需要重跑。

那 1/14 不匹配的是 D4-12「采购 8000 元谁审批」—— Day 4 期望 `needs_tool`，但 RAG 直接从条款答出了「部门主管、财务」。这其实暴露了一个设计问题：制度里写了审批规则，条款**足以**回答；但按规格又该走工具。Day 5 用意图路由解决了这个二义性（具体金额 → 工具，问规则本身 → RAG）。

评测脚本自己也会校验引用结构：`chunk_id` 必须真实存在于语料、`quote` 必须与原文逐字一致、`title/version/article/source_file/scope` 必须与语料元数据完全相符。

### 工具调用

`python -m scripts.evaluate_tools`，16 题：**14/16 通过**。两处失败：

1. **「查询火箭供应商」** — 期望 `{"category": "火箭"}`，实际 `{"keyword": "火箭"}`。这是真 bug：库里只有「办公设备」「电脑」两个品类，「火箭」是品类不是公司名。根因是路由的工具描述只说了「category 是品类，keyword 是供应商名称」，没说「X 供应商」这种句式里 X 该归哪边。本次 `count=0` 所以答案看不出差别，但如果库里真有家「火箭科技」，两个参数会查出不同结果。
2. **「普通员工出差坐高铁可以按什么座位等级报销」** — HTTP 502 `invalid_model_output`，偶发。这题走 RAG，同批次的拆单题（同样走 RAG）通过了，所以不是系统性问题。但**这个错误码把路由、起草、复核三个不同阶段的失败压成了一个**，日志里只留了 request_id，导致这次失败至今无法归因。

这两处都还没修。

### 关于这些数字

评测是开发用小样本，不是独立测试集，其结果不代表生产环境效果。状态匹配率和引用结构校验通过**都不等于回答正确率** —— 引用逐字一致只说明没编造出处，不说明结论真的被原文支持。所以：

- 第二层复核用的是同一个模型，它可能重复第一层的错误
- `human_review` 字段（content_correct / citations_support / conditions_preserved）需要人工逐题填写，目前都是 `null`
- 端到端脚本每题只跑一次，带 LLM 的评估单跑一次不足以判断稳定性（上面那个 502 就是例子）

不要把复核通过率说成准确率。

## 已知问题

按严重程度排列：

1. `check_day3.py` 默认预期值 10/30 已过期，直接跑会 `AssertionError`（需带参数，见上）。
2. `query_suppliers` 的 category / keyword 判定不准（见评测）。
3. `ModelOutputError` 缺阶段标签，502 无法归因。
4. `.env.example` 写 `text-embedding-v3`，与实际使用的 `text-embedding-v4` 不一致，照着配会触发索引失效。
5. `data/policies/` 下有 8 个 md 文件未纳入 manifest（`03_budget`、`04_supplier`、`05_acceptance`、`06_invoice`、`07_travel_request`、`08_hotel`、`09_transport`、`10_archive`）。其中 `08_hotel.md`（普通员工 350 / 部门经理 500）与已纳入的 `07_accommodation.md`（甲类 500 / 乙类 350，仅普通员工）**标准互相冲突**。目前 manifest 只收后者，前者是死数据；但只要哪天加载器改成扫描目录，就会同时索引两套冲突条款。
6. 评测报告每次覆盖同名文件，无历史版本，做不了回归对比。
7. `rag/evaluate.py` 逐题单独向量化（10 题 = 10 次 API 调用），`embed_texts` 本身支持批量。

## 设计要点

- **金额全程不用 float**：整数分存库 + Decimal 换算，接口返回字符串。边界验收覆盖 4999.99 / 5000 / 19999.99 / 20000 四个分界点。
- **结构化拒答分三种状态**：证据不足、材料冲突、缺少适用条件是三件不同的事。缺条件时列明缺失字段追问（`missing_fields`），不硬编答案。找不到规定不能推导成「公司禁止」或「公司允许」，也不用常识补全制度。
- **两层引用核验各有局限**：逐字一致只是第一层；同模型复核可能重复第一层的错误。所以保留人工评测，不把复核通过率说成准确率。
- **索引指纹**：模型、维度或语料任一变化，旧索引自动判定失效并报错，而不是悄悄返回错结果。
- **工具调用不信任任何一方**：参数与问题原文强绑定（区间、多金额、外币直接要求澄清），后端返回也要过一致性校验。渲染是确定性的，不经 LLM 改写，所以工具返回什么数字，用户就看到什么数字。

## 迭代记录

- **Day 2** — 模拟 OA 后端（FastAPI + SQLite：预算 / 供应商 / 审批链）
- **Day 3** — 制度条款切分与向量索引、余弦检索
- **Day 4** — 带两层引用核验的制度问答、结构化追问与拒答
- **Day 5** — 意图路由与工具调用（预算 / 审批链 / 供应商查询的参数绑定与一致性校验）
- **Day 6** — Docker Compose 容器化部署

## 限制

仅处理整理好的 Markdown 制度文件；不支持 PDF / Word 等格式。无会话记忆，不能从此前对话补全参数。模拟 OA 仅支持 CNY，不做汇率换算。
