from decimal import Decimal

RULE_VERSION = "demo-v1"


def get_approval_chain(amount: Decimal) -> tuple[str, list[str]]:
    if not amount.is_finite() or amount <= 0:
        raise ValueError("金额必须是有限正数")

    if amount < Decimal("5000"):
        return "PUR-001", ["部门主管"]

    if amount < Decimal("20000"):
        return "PUR-002", ["部门主管", "财务"]

    return "PUR-003", ["部门主管", "财务", "总经理"]