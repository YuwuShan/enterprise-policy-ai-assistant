import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from openai import APITimeoutError
from pydantic import ValidationError

from assistant import main as api
from assistant import service
from assistant.schemas import AskRequest, Draft, Review

HIT = {
    "chunk_id": "travel:demo-v1:第二条", "title": "差旅交通制度", "version": "demo-v1",
    "article": "第二条", "source_file": "06_travel_transport.md", "scope": "普通员工因公出差",
    "text": "第二条 普通员工因公乘坐高铁或动车，报销标准为二等座；乘坐飞机，报销标准为经济舱。",
    "score": 0.7,
}
PURCHASE_HIT = {
    "chunk_id": "purchase_request:demo-v1:第三条", "title": "采购申请制度", "version": "demo-v1",
    "article": "第三条", "source_file": "02_purchase_request.md",
    "scope": "本模拟企业采购申请的准备与提交",
    "text": "第三条 同一采购事项不得通过拆分金额、拆分申请单等方式绕过审批。"
            "审批金额按同一采购事项的合计金额计算。",
    "score": 0.7,
}
QUESTION = "普通员工因公乘坐高铁可以按什么座位等级报销？"


def draft_answer(chunk_id=None, quote=None, text="普通员工因公乘坐高铁，报销标准为二等座。"):
    return Draft(status="answer", claims=[{
        "text": text,
        "evidence": [{"chunk_id": chunk_id or HIT["chunk_id"], "quote": quote or HIT["text"]}],
    }])


class Day4Tests(unittest.TestCase):
    def run_flow(self, *outputs, question=QUESTION, hits=None):
        with patch.object(service, "search", return_value=[HIT] if hits is None else hits), \
             patch.object(service, "ask_model", side_effect=outputs):
            return service.answer_question(question)

    def test_rule_question_reaches_model(self):
        question = "为了少走审批，可以把同一笔采购拆成几张小额申请吗？"
        draft = Draft(status="answer", claims=[{
            "text": "不可以，审批金额按同一采购事项的合计金额计算。",
            "evidence": [{
                "chunk_id": PURCHASE_HIT["chunk_id"],
                "quote": "同一采购事项不得通过拆分金额、拆分申请单等方式绕过审批。",
            }],
        }])
        with patch.object(service, "search", return_value=[PURCHASE_HIT]) as retrieve, \
             patch.object(service, "ask_model",
                           side_effect=[draft, Review(verdict="supported")]) as ask:
            result = service.answer_question(question)
        retrieve.assert_called_once()
        self.assertEqual(result.status, "answer")
        self.assertEqual(result.citations[0].chunk_id, PURCHASE_HIT["chunk_id"])
        self.assertEqual(result.citations[0].source_file, "02_purchase_request.md")
        self.assertIn("[1]", result.answer)
        self.assertEqual(ask.call_count, 2)

    def test_scope_question_reaches_model(self):
        draft = Draft(status="answer", claims=[{
            "text": "适用于本模拟企业所有人民币采购。",
            "evidence": [{"chunk_id": HIT["chunk_id"], "quote": HIT["text"]}],
        }])
        with patch.object(service, "search", return_value=[HIT]) as retrieve, \
             patch.object(service, "ask_model",
                           side_effect=[draft, Review(verdict="supported")]):
            result = service.answer_question("采购审批制度适用于哪些范围？")
        retrieve.assert_called_once()
        self.assertEqual(result.status, "answer")

    def test_supported_answer_has_server_sources(self):
        result = self.run_flow(draft_answer(), Review(verdict="supported"))
        self.assertEqual(result.status, "answer")
        self.assertIn("[1]", result.answer)
        self.assertEqual(result.citations[0].source_file, HIT["source_file"])

    def test_unknown_citation_is_rejected(self):
        result = self.run_flow(draft_answer(chunk_id="fake:第99条"))
        self.assertEqual(result.reason, "citation_check_failed")
        self.assertEqual(result.citations, [])

    def test_fabricated_quote_is_rejected(self):
        result = self.run_flow(draft_answer(quote="所有员工都可以报销商务舱。"))
        self.assertEqual(result.reason, "citation_check_failed")

    def test_real_quote_does_not_prove_claim(self):
        result = self.run_flow(draft_answer(text="可以报销商务舱。"), Review(verdict="unsupported"))
        self.assertEqual(result.status, "refuse")
        self.assertEqual(result.reason, "unsupported")

    def test_conflict(self):
        result = self.run_flow(draft_answer(), Review(verdict="conflict"))
        self.assertEqual(result.reason, "conflict")

    def test_review_missing_context(self):
        result = self.run_flow(draft_answer(), Review(verdict="missing_context", missing_fields=["员工身份"]))
        self.assertEqual(result.status, "clarify")
        self.assertEqual(result.citations, [])

    def test_initial_clarify(self):
        result = self.run_flow(Draft(status="clarify", missing_fields=["出差城市", "员工身份"]))
        self.assertEqual(result.status, "clarify")
        self.assertIn("重新提交完整问题", result.answer)

    def test_initial_refusal(self):
        result = self.run_flow(Draft(status="refuse"))
        self.assertEqual(result.status, "refuse")
        self.assertNotIn("公司禁止", result.answer)

    def test_empty_retrieval_does_not_call_model(self):
        result = self.run_flow(hits=[])
        self.assertEqual(result.reason, "insufficient_evidence")


    def test_model_can_request_tool(self):
        result = self.run_flow(Draft(status="needs_tool"))
        self.assertEqual(result.status, "needs_tool")

    def test_needs_tool_decided_after_retrieval(self):
        # side_effect 只给一个输出：needs_tool 必须在 draft 阶段返回，
        # 若继续调用 review 会触发 StopIteration 而使测试失败。
        for question in ("采购8000元谁审批？", "研发部剩余预算多少？", "查询供应商名录"):
            with self.subTest(question=question):
                result = self.run_flow(Draft(status="needs_tool"), question=question)
                self.assertEqual(result.status, "needs_tool")
                self.assertEqual(result.reason, "requires_oa")
                self.assertEqual(result.citations, [])
                self.assertEqual(result.missing_fields, [])
                self.assertTrue(result.answer)

    def test_json_parse_error(self):
        with self.assertRaises(service.ModelOutputError):
            service.parse_output("不是JSON", Draft)

    def test_empty_answer_is_invalid(self):
        with self.assertRaises(ValidationError):
            Draft(status="answer")

    def test_uncited_claim_is_invalid(self):
        with self.assertRaises(ValidationError):
            Draft(status="answer", claims=[{"text": "随便编写", "evidence": []}])

    def test_refusal_cannot_contain_claims(self):
        with self.assertRaises(ValidationError):
            Draft(status="refuse", claims=draft_answer().claims)

    def test_unknown_source_fields_invalid(self):
        with self.assertRaises(ValidationError):
            Draft(status="refuse", title="伪造制度")

    def test_request_constraints(self):
        for text in ("", "   ", "字" * 1001):
            with self.subTest(text=text[:10]), self.assertRaises(ValidationError):
                AskRequest(question=text)

    def test_index_failure_is_503(self):
        with patch.object(api, "answer_question", side_effect=service.KnowledgeUnavailable("test")):
            with self.assertRaises(HTTPException) as caught:
                api.ask(AskRequest(question=QUESTION))
        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.detail["code"], "knowledge_unavailable")

    def test_bad_model_output_is_502(self):
        with patch.object(api, "answer_question", side_effect=service.ModelOutputError("test")):
            with self.assertRaises(HTTPException) as caught:
                api.ask(AskRequest(question=QUESTION))
        self.assertEqual(caught.exception.status_code, 502)

    def test_timeout_is_504(self):
        error = APITimeoutError(request=Mock())
        with patch.object(api, "answer_question", side_effect=error):
            with self.assertRaises(HTTPException) as caught:
                api.ask(AskRequest(question=QUESTION))
        self.assertEqual(caught.exception.status_code, 504)

    def test_request_id_present(self):
        result = service.non_answer(QUESTION, "refuse", "insufficient_evidence")
        with patch.object(api, "answer_question", return_value=result):
            response = api.ask(AskRequest(question=QUESTION))
        self.assertEqual(len(response.request_id), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
