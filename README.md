# enterprise-policy-ai-assistant
## Day 2：模拟 OA 后端

本项目使用模拟企业数据。

### 初始化与启动

在项目根目录执行：

- `.\.venv\Scripts\python.exe -m oa.db`
- `.\.venv\Scripts\python.exe -m uvicorn oa.main:app --reload --host 127.0.0.1 --port 8001`

另开终端执行验收：

- `.\.venv\Scripts\python.exe .\check_day2.py`

### 接口

- GET /budgets：按部门和月份查询预算。
- GET /suppliers：按品类、关键词、状态查询供应商。
- POST /approval-chain：按金额返回审批链。

### 约定

- 预算在数据库中以整数分保存，接口以元的字符串返回。
- 审批金额使用 Decimal。
- 目前仅支持 CNY。
- 审批链由 Python 规则决定。
- 初始化只补充缺失记录，不覆盖已有数据。
- 初始预算月份为 2026-10。
- 查询审批链不会扣减预算或执行审批。

## Day 3：制度条款检索

### 资料
- 10 份模拟制度。
- 30 条条款。
- 按“第 X 条”切分，保留条款子项。
- 保存制度名称、版本、适用范围和原文件名。

### 检索
- 模型：text-embedding-v4。
- 向量维度：1024。
- 向量归一化后使用点积计算余弦相似度。
- 默认返回前 5 条原文。

### 运行
- python -m rag.documents
- python -m rag.build_index
- python -m rag.search "你的问题"
- python check_day3.py
- python -m rag.evaluate

以上命令均使用项目虚拟环境中的 Python。

### 实际评估结果
- 测试问题数：10。
- Top-1 命中：填写实际结果。
- Top-5 命中：填写实际结果。
- 失败问题及分析：填写实际情况。

### 当前限制
- 仅处理整理好的 Markdown 制度。
- 尚未生成回答、核验引用或判断拒答。




