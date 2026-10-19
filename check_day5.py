"""Offline: no real model request, no real OA request, no API key needed."""
import io
import json
import unittest
from datetime import date
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from fastapi import HTTPException

from assistant import main as api, oa_client, orchestrator as flow, router
from assistant.router import ApprovalArgs, BudgetArgs, PolicyArgs, Selection, SupplierArgs
from assistant.schemas import AskRequest, AskResponse
from assistant.service import ModelOutputError

BUDGET = {"department": "研发部", "month": "2026-10", "currency": "CNY",
          "total": "100000.00", "used": "25000.00", "remaining": "75000.00"}
APPROVAL = {"amount": "8000.00", "currency": "CNY", "chain": ["部门主管", "财务"],
            "rule_id": "PUR-002", "rule_version": "demo-v1"}


def completion(name="query_budget", args=None, count=1):
    args = {} if args is None else args
    call = NS(type="function", function=NS(name=name, arguments=json.dumps(args)))
    return NS(choices=[NS(finish_reason="tool_calls", message=NS(tool_calls=[call] * count))])


class RouterTests(unittest.TestCase):
    def test_known_selection(self):
        result = router.decode_selection(completion(args={"department": "研发部", "month_text": "本月"}))
        self.assertEqual(result.args.month_text, "本月")

    def test_unknown_function_rejected(self):
        with self.assertRaises(ModelOutputError):
            router.decode_selection(completion(name="os.system"))

    def test_zero_or_multiple_calls_rejected(self):
        for count in (0, 2):
            with self.subTest(count=count), self.assertRaises(ModelOutputError):
                router.decode_selection(completion(count=count))

    def test_unknown_argument_rejected(self):
        with self.assertRaises(ModelOutputError):
            router.decode_selection(completion(args={"url": "https://example.invalid"}))

    def test_invalid_json_rejected(self):
        response = completion()
        response.choices[0].message.tool_calls[0].function.arguments = "not json"
        with self.assertRaises(ModelOutputError):
            router.decode_selection(response)

    def test_truncated_output_rejected(self):
        response = completion()
        response.choices[0].finish_reason = "length"
        with self.assertRaises(ModelOutputError):
            router.decode_selection(response)

    def test_router_error_runs_no_action(self):
        with patch.object(flow, "select_action", side_effect=ModelOutputError("test")), \
             patch.object(flow, "call_oa") as oa, patch.object(flow, "answer_policy") as rag:
            with self.assertRaises(ModelOutputError):
                flow.handle_question("test")
        oa.assert_not_called()
        rag.assert_not_called()


class ArgumentTests(unittest.TestCase):
    def test_month_formats_and_year_rollover(self):
        for text, today, expected in [("2026年9月", date(2026, 10, 19), "2026-09"),
                                      ("本月", date(2026, 10, 19), "2026-10"),
                                      ("上月", date(2026, 1, 1), "2025-12")]:
            with self.subTest(text=text):
                self.assertEqual(flow.normalize_month(text, today), expected)

    def test_invalid_month(self):
        for text in ("2026-13", "下个月", "10月"):
            with self.subTest(text=text), self.assertRaises(flow.NeedClarification):
                flow.normalize_month(text)

    def test_amount_conversion(self):
        for text, expected in [("3万元", "30000.00"), ("1,234.56元", "1234.56"), ("0.01元", "0.01")]:
            with self.subTest(text=text):
                self.assertEqual(flow.normalize_amount(text, "采购" + text)["amount"], expected)

    def test_invalid_amounts(self):
        for text in ("0元", "-1元", "1.001元", "1e4元", "NaN元", "10000000000元", "一万元"):
            with self.subTest(text=text), self.assertRaises(flow.NeedClarification):
                flow.normalize_amount(text, "采购" + text)

    def test_currency_not_assumed_or_converted(self):
        for text in ("8000", "8000美元", "8000港币"):
            with self.subTest(text=text), self.assertRaises(flow.NeedClarification) as caught:
                flow.normalize_amount(text, "采购" + text)
            self.assertIn("币种", caught.exception.fields)

    def test_amount_must_be_complete_source_span(self):
        for text, question in [("8000元", "采购18000元"), ("3", "采购3万元"), ("8000元", "采购负 8000元")]:
            with self.subTest(question=question), self.assertRaises(flow.NeedClarification):
                flow.normalize_amount(text, question)

    def test_multiple_amounts_and_range_rejected(self):
        for question in ("采购5000到8000元", "采购5000元和8000元", "采购5000+8000元"):
            with self.subTest(question=question), self.assertRaises(flow.NeedClarification):
                flow.normalize_amount("8000元", question)

    def test_budget_missing_fields(self):
        with self.assertRaises(flow.NeedClarification) as caught:
            flow.prepare_arguments(Selection("query_budget", BudgetArgs()), "预算多少")
        self.assertEqual(caught.exception.fields, ["所属部门", "查询月份"])

    def test_invented_department_rejected(self):
        with self.assertRaises(flow.NeedClarification):
            flow.prepare_arguments(Selection("query_budget", BudgetArgs(department="研发部", month_text="本月")), "我本月预算多少")

    def test_supplier_filters_preserved(self):
        selection = Selection("query_suppliers", SupplierArgs(category="电脑", status_text="停用"))
        self.assertEqual(flow.prepare_arguments(selection, "查询停用的电脑供应商"), {"category": "电脑", "status": "inactive"})

    def test_no_implicit_supplier_filter(self):
        self.assertEqual(flow.prepare_arguments(Selection("query_suppliers", SupplierArgs()), "查询供应商名录"), {})


class FlowTests(unittest.TestCase):
    def test_policy_bypasses_oa(self):
        question = "为了少走审批，可以把同一笔采购拆成几张小额申请吗？"
        expected = AskResponse(question=question, status="refuse", answer="test", reason="test")
        with patch.object(flow, "select_action", return_value=Selection("consult_policy", PolicyArgs())), \
             patch.object(flow, "answer_policy", return_value=expected) as rag, patch.object(flow, "call_oa") as oa:
            self.assertEqual(flow.handle_question(question), expected)
        rag.assert_called_once_with(question)
        oa.assert_not_called()

    def test_budget_bypasses_rag_and_has_trace(self):
        with patch.object(flow, "select_action", return_value=Selection("query_budget", BudgetArgs(department="研发部", month_text="2026-10"))), \
             patch.object(flow, "answer_policy", side_effect=RuntimeError("index down")) as rag, \
             patch.object(flow, "call_oa", return_value=BUDGET) as oa:
            result = flow.handle_question("研发部2026-10预算多少")
        rag.assert_not_called()
        oa.assert_called_once_with("query_budget", {"department": "研发部", "month": "2026-10"})
        self.assertIn("75000.00", result.answer)
        self.assertEqual(result.tool.data, BUDGET)
        self.assertEqual(result.citations, [])
        self.assertEqual(result.mode, "tool")

    def test_missing_fields_do_not_call_oa(self):
        with patch.object(flow, "select_action", return_value=Selection("query_budget", BudgetArgs())), patch.object(flow, "call_oa") as oa:
            result = flow.handle_question("预算多少")
        oa.assert_not_called()
        self.assertEqual(result.status, "clarify")

    def test_budget_not_found_is_not_zero(self):
        with patch.object(flow, "select_action", return_value=Selection("query_budget", BudgetArgs(department="不存在部", month_text="2026-10"))), \
             patch.object(flow, "call_oa", side_effect=oa_client.BudgetNotFound):
            result = flow.handle_question("不存在部2026-10预算")
        self.assertEqual(result.status, "not_found")
        self.assertIsNone(result.tool.data)

    def test_empty_suppliers_is_answer(self):
        with patch.object(flow, "select_action", return_value=Selection("query_suppliers", SupplierArgs())), \
             patch.object(flow, "call_oa", return_value={"count": 0, "items": []}):
            result = flow.handle_question("查询供应商名录")
        self.assertEqual(result.status, "answer")
        self.assertIn("未找到", result.answer)

    def test_approval_chain_uses_oa_output(self):
        with patch.object(flow, "select_action", return_value=Selection("get_approval_chain", ApprovalArgs(amount_text="8000元"))), \
             patch.object(flow, "call_oa", return_value=APPROVAL):
            result = flow.handle_question("采购8000元谁审批")
        self.assertIn("部门主管 → 财务", result.answer)
        self.assertEqual(result.tool.data["rule_id"], "PUR-002")

    def test_response_mismatch_rejected(self):
        for data in ({**BUDGET, "remaining": "1.00"}, {**BUDGET, "department": "市场部"}, {**BUDGET, "total": "NaN"}):
            with self.subTest(data=data), self.assertRaises(oa_client.OAError):
                flow.render_tool("query_budget", {"department": "研发部", "month": "2026-10"}, data)

    def test_api_oa_errors_are_not_refusals(self):
        for status, code in ((503, "oa_unavailable"), (504, "oa_timeout"), (502, "oa_bad_response")):
            with self.subTest(status=status), patch.object(api, "answer_question", side_effect=oa_client.OAError(code, status)):
                with self.assertRaises(HTTPException) as caught:
                    api.ask(AskRequest(question="预算多少"))
                self.assertEqual(caught.exception.status_code, status)
                self.assertEqual(caught.exception.detail["code"], code)


class HTTPClientTests(unittest.TestCase):
    def test_connection_error(self):
        with patch.object(oa_client, "build_opener") as factory:
            factory.return_value.open.side_effect = URLError("connection refused")
            with self.assertRaises(oa_client.OAError) as caught:
                oa_client.call_oa("query_suppliers", {})
        self.assertEqual(caught.exception.http_status, 503)

    def test_timeout(self):
        with patch.object(oa_client, "build_opener") as factory:
            factory.return_value.open.side_effect = TimeoutError()
            with self.assertRaises(oa_client.OAError) as caught:
                oa_client.call_oa("query_suppliers", {})
        self.assertEqual(caught.exception.http_status, 504)

    def test_budget_404(self):
        with patch.object(oa_client, "build_opener") as factory:
            factory.return_value.open.side_effect = HTTPError("http://local", 404, "not found", {}, io.BytesIO(b"{}"))
            with self.assertRaises(oa_client.BudgetNotFound):
                oa_client.call_oa("query_budget", {"department": "x", "month": "2026-10"})

    def test_invalid_response_json(self):
        with patch.object(oa_client, "build_opener") as factory:
            factory.return_value.open.return_value.__enter__.return_value.read.return_value = b"invalid"
            with self.assertRaises(oa_client.OAError) as caught:
                oa_client.call_oa("query_suppliers", {})
        self.assertEqual(caught.exception.http_status, 502)

    def test_fixed_post_endpoint_and_json(self):
        with patch.object(oa_client, "build_opener") as factory:
            factory.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(APPROVAL).encode()
            oa_client.call_oa("get_approval_chain", {"amount": "8000.00", "currency": "CNY"})
            request = factory.return_value.open.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/approval-chain"))
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data)["amount"], "8000.00")


if __name__ == "__main__":
    unittest.main(verbosity=2)
