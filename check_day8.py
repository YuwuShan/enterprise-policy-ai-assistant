"""Offline tests for financial boundaries and the evaluation checker."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import unittest

from oa.rules import get_approval_chain
from quality.checks import grade, metrics
from quality.evaluate import load_cases, valid_base
from rag.documents import load_chunks

CASES, SOURCES = load_cases()


def body(case):
    return {"question":case["question"], "status":case["expected"]["status"],
            "answer":"测试答案", "reason":"test", "request_id":"test-request",
            "citations":[], "missing_fields":[], "mode":case["expected"].get("mode","rag"), "tool":None}


class RulesTests(unittest.TestCase):
    def test_boundaries(self):
        for value, rule, chain in [
            ("4999.99","PUR-001",["部门主管"]),
            ("5000.00","PUR-002",["部门主管","财务"]),
            ("19999.99","PUR-002",["部门主管","财务"]),
            ("20000.00","PUR-003",["部门主管","财务","总经理"]),
        ]:
            with self.subTest(value=value):
                self.assertEqual(get_approval_chain(Decimal(value)), (rule,chain))

    def test_invalid_values(self):
        for value in ("0","-1","NaN","Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                get_approval_chain(Decimal(value))


class EvaluationTests(unittest.TestCase):
    def test_dataset_has_24_unique_questions_and_existing_sources(self):
        self.assertEqual(len(CASES),24)
        self.assertEqual(len({c['question'] for c in CASES}),24)

    def test_http_error_is_not_business_refusal(self):
        case = CASES[-1]
        self.assertFalse(all(grade(case,503,{"detail":{"code":"model_connection"}},SOURCES).values()))

    def test_empty_or_nonobject_body_fails(self):
        for value in ([],None,{},"invalid"):
            self.assertFalse(all(grade(CASES[0],200,value,SOURCES).values()))

    def test_wrong_approval_chain_fails(self):
        case = CASES[8]  # 20000 CNY
        result = body(case)
        result["tool"] = {"name":case["expected"]["tool"], "arguments":case["expected"]["arguments"],
                          "endpoint":"/approval-chain", "queried_at":"2026-10-22T00:00:00Z", "data":deepcopy(case["expected"]["data"])}
        self.assertTrue(all(grade(case,200,result,SOURCES).values()))
        result["tool"]["data"]["chain"] = ["部门主管"]
        self.assertFalse(grade(case,200,result,SOURCES)["tool_data"])

    def test_citation_must_match_original_and_metadata(self):
        case = CASES[14]
        hit = SOURCES[case['expected']['source']]
        result = body(case)
        result['answer'] = case['rubric'] + ' [1]'
        result['citations'] = [{**{k:hit[k] for k in ('chunk_id','title','version','article','source_file','scope')},
                                'number':1,'quote':hit['text']}]
        self.assertTrue(all(grade(case,200,result,SOURCES).values()))
        result['citations'][0]['quote'] = '这是一句编造的条款'
        self.assertFalse(grade(case,200,result,SOURCES)['citation_integrity'])

    def test_non_answer_cannot_carry_citations(self):
        case = CASES[-1]
        hit = next(iter(SOURCES.values()))
        result = body(case)
        result['citations'] = [{**{k:hit[k] for k in ('chunk_id','title','version','article','source_file','scope')},
                                'number':1,'quote':hit['text']}]
        self.assertFalse(grade(case,200,result,SOURCES)['non_answer_has_no_citations'])

    def test_unreviewed_is_not_counted_as_human_pass(self):
        result = metrics([{'automatic_pass':True,'human_ok':None}])
        self.assertEqual(result['reviewed'],0)
        self.assertIsNone(result['human_pass_all'])
        self.assertIsNone(result['complete_pass_all'])

    def test_auto_pass_does_not_override_human_failure(self):
        result = metrics([{'automatic_pass':True,'human_ok':False}])
        self.assertEqual(result['complete_pass_all'],0)

    def test_unsafe_base_urls_are_rejected(self):
        for url in ('http://oa.jacewood.work','https://demo:secret@oa.jacewood.work','https://oa.jacewood.work/ask','https://oa.jacewood.work?x=1'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                valid_base(url)
        self.assertEqual(valid_base('https://oa.jacewood.work/'),'https://oa.jacewood.work')


if __name__ == '__main__':
    unittest.main(verbosity=2)
