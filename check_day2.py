import json
import os
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = os.getenv("OA_BASE_URL", "http://127.0.0.1:8001")


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            return error.code, json.load(error)


def main():
    path = "/budgets?" + urlencode({"department": "研发部", "month": "2026-10"})
    code, result = request(path)
    assert code == 200, (code, result)
    assert (result["total"], result["used"], result["remaining"]) == (
        "100000.00", "25000.00", "75000.00"
    ), result

    for department, month, expected in [
        ("不存在的部门", "2026-10", 404),
        ("研发部", "2026-11", 404),
        ("研发部", "2026-13", 422),
        ("   ", "2026-10", 422),
    ]:
        code, result = request("/budgets?" + urlencode({
            "department": department, "month": month,
        }))
        assert code == expected, (department, month, code, result)

    code, result = request("/suppliers?" + urlencode({"category": "电脑"}))
    assert code == 200 and result["count"] == 2, (code, result)
    assert {item["status"] for item in result["items"]} == {"active", "inactive"}

    code, result = request("/suppliers?" + urlencode({"category": "电脑", "status": "active"}))
    assert code == 200 and [x["id"] for x in result["items"]] == ["SUP002"], (code, result)

    code, result = request("/suppliers?" + urlencode({"keyword": "不存在的名字"}))
    assert code == 200 and result == {"count": 0, "items": []}, (code, result)

    for amount, rule, chain in [
        ("0.01", "PUR-001", ["部门主管"]),
        ("4999.99", "PUR-001", ["部门主管"]),
        ("5000.00", "PUR-002", ["部门主管", "财务"]),
        ("19999.99", "PUR-002", ["部门主管", "财务"]),
        ("20000.00", "PUR-003", ["部门主管", "财务", "总经理"]),
    ]:
        code, result = request("/approval-chain", {"amount": amount, "currency": "CNY"})
        assert code == 200, (amount, code, result)
        assert (result["rule_id"], result["chain"]) == (rule, chain), result
        assert result["amount"] == amount and result["rule_version"] == "demo-v1", result

    for payload in [
        {"amount": "0", "currency": "CNY"},
        {"amount": "-1", "currency": "CNY"},
        {"amount": "1.001", "currency": "CNY"},
        {"amount": "NaN", "currency": "CNY"},
        {"amount": "5000", "currency": "USD"},
        {"currency": "CNY"},
        {"amount": "5000", "currency": "CNY", "chain": ["总经理"]},
    ]:
        code, result = request("/approval-chain", payload)
        assert code == 422, (payload, code, result)

    print("Day 2 验收通过：预算、供应商、审批边界与非法输入。")


if __name__ == "__main__":
    main()
