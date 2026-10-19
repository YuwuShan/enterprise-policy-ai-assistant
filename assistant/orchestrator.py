"""Step 3: validate arguments, dispatch one action and render verifiable data."""
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from assistant.oa_client import BudgetNotFound, ENDPOINTS, OAError, call_oa
from assistant.router import select_action
from assistant.schemas import AskResponse, ToolTrace
from assistant.service import answer_question as answer_policy
from oa.schemas import ApprovalRequest

BUSINESS_TZ = timezone(timedelta(hours=8))
STATUS_WORDS = {"正常": "active", "启用": "active", "可用": "active", "active": "active",
                "停用": "inactive", "已停用": "inactive", "inactive": "inactive"}


class NeedClarification(Exception):
    def __init__(self, fields, message):
        self.fields, self.message = fields, message


def source_value(value, question, field):
    if value is None:
        raise NeedClarification([field], f"请提供{field}，并重新提交完整问题。")
    if value not in question:
        raise NeedClarification([field], f"未能从原问题确认{field}，请明确填写后重试。")
    return value


def normalize_month(text, today=None):
    today = today or datetime.now(BUSINESS_TZ).date()
    if text == "本月":
        return today.strftime("%Y-%m")
    if text == "上月":
        return (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    match = re.fullmatch(r"([1-9][0-9]{3})(?:-([0-9]{1,2})|年([0-9]{1,2})月)", text)
    if match:
        year, month = int(match[1]), int(match[2] or match[3])
        try:
            return date(year, month, 1).strftime("%Y-%m")
        except ValueError:
            pass
    raise NeedClarification(["查询月份"], "请使用2026-10、2026年10月、本月或上月，并重新提交完整问题。")


def normalize_amount(text, question):
    text = source_value(text, question, "金额")
    if re.search(r"[0-9][0-9,.]*\s*(?:到|至|[-~～—+*/×÷])\s*[0-9]", question) or len(re.findall(r"[0-9][0-9,.]*\s*万?\s*(?:元|人民币|CNY)", question, re.IGNORECASE)) > 1:
        raise NeedClarification(["金额"], "请一次提供一笔确定的采购金额，不要使用区间、算式或多个金额。")
    # Match the longest currency names first: 美元 must not become 元.
    words = re.findall(r"人民币|美元|港币|日元|欧元|CNY|USD|HKD|JPY|EUR|元", question.upper())
    if not words:
        raise NeedClarification(["币种"], "请明确币种，例如采购8000元；当前模拟OA只支持人民币。")
    if any(word not in ("人民币", "CNY", "元") for word in words):
        raise NeedClarification(["币种"], "当前模拟OA仅支持人民币，不会自动换汇。请确认业务币种。")
    # This lesson deliberately accepts only one complete Arabic-number amount.
    pattern = r"(?:人民币|CNY)?\s*((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)\s*(万)?\s*(?:元|CNY)?"
    match = re.fullmatch(pattern, text, re.IGNORECASE)
    if not match:
        raise NeedClarification(["金额"], "请提供单笔明确金额，例如8000元或3万元；暂不处理区间、算式和中文大写金额。")
    # Reject extraction of 8000 from 18000, or 3 from 3万元.
    start = question.find(text)
    before, after = question[:start].rstrip(), question[start + len(text):].lstrip()
    if (before and before[-1] in "0123456789.,-负") or (after and after[0] in "0123456789.,万元"):
        raise NeedClarification(["金额"], "提取金额不完整，请重新提供完整金额和币种。")
    amount = Decimal(match[1].replace(",", "")) * (10000 if match[2] else 1)
    try:
        request = ApprovalRequest(amount=amount, currency="CNY")
    except ValidationError as error:
        raise NeedClarification(["金额"], "金额必须大于0，最多两位小数且不超过9999999999.99元。") from error
    return {"amount": format(request.amount, ".2f"), "currency": "CNY"}


def prepare_arguments(selection, question):
    args = selection.args
    if selection.name == "query_budget":
        missing = [label for value, label in ((args.department, "所属部门"), (args.month_text, "查询月份")) if value is None]
        if missing:
            raise NeedClarification(missing, "请补充" + "、".join(missing) + "，然后重新提交完整问题。")
        department = source_value(args.department, question, "所属部门")
        month = normalize_month(source_value(args.month_text, question, "查询月份"))
        return {"department": department, "month": month}
    if selection.name == "get_approval_chain":
        return normalize_amount(args.amount_text, question)
    if selection.name == "query_suppliers":
        result = {}
        for field in ("category", "keyword"):
            value = getattr(args, field)
            if value is not None:
                result[field] = source_value(value, question, "业务场景")
        if args.status_text is not None:
            word = source_value(args.status_text, question, "业务场景")
            if word not in STATUS_WORDS:
                raise NeedClarification(["业务场景"], "请明确供应商状态为正常或停用，或不设置状态筛选。")
            result["status"] = STATUS_WORDS[word]
        return result
    raise RuntimeError("程序传入了未知动作")


def money(text):
    if not isinstance(text, str) or not re.fullmatch(r"[0-9]+\.[0-9]{2}", text):
        raise OAError("oa_bad_response", 502)
    return Decimal(text)


def render_tool(name, args, data):
    """Validate correlation to the request, then render data without an LLM."""
    try:
        if name == "query_budget":
            if data["department"] != args["department"] or data["month"] != args["month"] or data["currency"] != "CNY":
                raise ValueError("预算响应与请求不匹配")
            total, used, remaining = (money(data[k]) for k in ("total", "used", "remaining"))
            if remaining != total - used:
                raise ValueError("预算数据不一致")
            return f'{data["department"]} {data["month"]}预算：总额{total:.2f}元，已用{used:.2f}元，剩余{remaining:.2f}元。'
        if name == "get_approval_chain":
            if money(data["amount"]) != Decimal(args["amount"]) or data["currency"] != "CNY" or not data["chain"] or not all(data["chain"]):
                raise ValueError("审批响应与请求不匹配")
            return f'采购金额{data["amount"]}元，审批链：' + " → ".join(data["chain"]) + f'。规则：{data["rule_id"]}，版本：{data["rule_version"]}。'
        if data["count"] != len(data["items"]):
            raise ValueError("供应商数量不一致")
        for item in data["items"]:
            if any(item[k] != args[k] for k in ("category", "status") if k in args):
                raise ValueError("筛选结果不匹配")
            if "keyword" in args and args["keyword"] not in item["name"]:
                raise ValueError("供应商名称不匹配")
        if not data["items"]:
            return "未找到符合筛选条件的供应商。"
        lines = [f'找到{data["count"]}家供应商：']
        lines += [f'{item["id"]} {item["name"]}，{item["category"]}，' + ("正常" if item["status"] == "active" else "停用") for item in data["items"]]
        return "\n".join(lines)
    except (KeyError, ValueError, TypeError, InvalidOperation) as error:
        raise OAError("oa_bad_response", 502) from error


def handle_question(question):
    selection = select_action(question)
    if selection.name == "consult_policy":
        return answer_policy(question)
    try:
        if selection.name == "ask_clarification":
            raise NeedClarification(selection.args.missing_fields, "请一次只提一个明确查询，并补齐所需条件后重新提交完整问题。")
        args = prepare_arguments(selection, question)
    except NeedClarification as error:
        return AskResponse(question=question, status="clarify", reason="missing_or_invalid_arguments",
                           answer=error.message, missing_fields=error.fields, mode="router")
    trace = ToolTrace(name=selection.name, arguments=args, endpoint=ENDPOINTS[selection.name][1],
                      queried_at=datetime.now(BUSINESS_TZ).isoformat(timespec="seconds"))
    try:
        data = call_oa(selection.name, args)
    except BudgetNotFound:
        return AskResponse(question=question, status="not_found", reason="budget_not_found",
                           answer=f'未找到{args["department"]} {args["month"]}的预算记录，不能据此认定预算为0。', mode="tool", tool=trace)
    answer = render_tool(selection.name, args, data)
    return AskResponse(question=question, status="answer", reason="oa_result", answer=answer,
                       mode="tool", tool=trace.model_copy(update={"data": data}))
