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