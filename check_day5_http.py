"""Two real local HTTP servers. Model decisions are fixtures; no paid API calls.
Creates data/index/day5_http_test.db; does not touch data/oa.db.
"""
import json
import os
import asyncio
import socket
import threading
import time
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import uvicorn
from assistant import orchestrator as flow
from assistant.main import app as assistant_app
from assistant.router import ApprovalArgs, BudgetArgs, PolicyArgs, Selection, SupplierArgs
from assistant.schemas import AskResponse
from oa import db
from oa.main import app as oa_app


def start_server(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() >= deadline:
            server.should_exit = True
            thread.join(timeout=5)
            sock.close()
            raise RuntimeError("测试服务器启动失败")
        time.sleep(0.05)
    return server, thread, sock, port


def stop_server(item):
    server, thread, sock, _ = item
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


def run():
    # Python 3.12 / Windows: avoid Proactor close callbacks in the threaded test servers.
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    db.DB_PATH = Path(__file__).resolve().parent / "data/index/day5_http_test.db"
    db.initialize()
    servers = []
    count = 0
    try:
        oa = start_server(oa_app)
        servers.append(oa)
        assistant = start_server(assistant_app)
        servers.append(assistant)
        opener = build_opener(ProxyHandler({}))

        def request(question):
            body = json.dumps({"question": question}, ensure_ascii=False).encode("utf-8")
            req = Request(f"http://127.0.0.1:{assistant[3]}/ask", data=body, headers={"Content-Type": "application/json"})
            try:
                with opener.open(req, timeout=10) as response:
                    return response.status, json.load(response)
            except HTTPError as error:
                with error:
                    return error.code, json.load(error)

        def check(question, selection, assertion):
            nonlocal count
            with patch.object(flow, "select_action", return_value=selection):
                status, body = request(question)
            assert status == 200, body
            assert body["request_id"]
            assertion(body)
            count += 1

        def equal(actual, expected):
            assert actual == expected, (actual, expected)

        with patch.dict(os.environ, {"OA_BASE_URL": f"http://127.0.0.1:{oa[3]}"}):
            check("研发部2026-10预算", Selection("query_budget", BudgetArgs(department="研发部", month_text="2026-10")),
                  lambda b: equal(b["tool"]["data"]["remaining"], "75000.00"))
            for amount, rule in (("4999.99", "PUR-001"), ("5000", "PUR-002"), ("19999.99", "PUR-002"), ("20000", "PUR-003"), ("3万", "PUR-003")):
                check(f"采购{amount}元谁审批", Selection("get_approval_chain", ApprovalArgs(amount_text=f"{amount}元")),
                      lambda b, rule=rule: equal(b["tool"]["data"]["rule_id"], rule))
            check("查询停用的电脑供应商", Selection("query_suppliers", SupplierArgs(category="电脑", status_text="停用")),
                  lambda b: equal([i["id"] for i in b["tool"]["data"]["items"]], ["SUP003"]))
            check("查询火箭供应商", Selection("query_suppliers", SupplierArgs(category="火箭")),
                  lambda b: equal((b["status"], b["tool"]["data"]["count"]), ("answer", 0)))
            check("不存在部2026-10预算", Selection("query_budget", BudgetArgs(department="不存在部", month_text="2026-10")),
                  lambda b: equal(b["status"], "not_found"))
            check("预算多少", Selection("query_budget", BudgetArgs()), lambda b: equal(b["status"], "clarify"))
            for question in ("采购可以拆单少走审批吗", "采购审批制度适用于哪些范围"):
                fixture = AskResponse(question=question, status="refuse", answer="测试用RAG响应", reason="test")
                with patch.object(flow, "answer_policy", return_value=fixture):
                    check(question, Selection("consult_policy", PolicyArgs()), lambda b: equal(b["mode"], "rag"))
            # Stop only the test OA server, then confirm assistant exposes dependency failure.
            stop_server(oa)
            servers.remove(oa)
            with patch.object(flow, "select_action", return_value=Selection("query_suppliers", SupplierArgs())):
                status, body = request("查询供应商名录")
            equal(status, 503)
            equal(body["detail"]["code"], "oa_unavailable")
            count += 1
        print(f"HTTP checks passed: {count}. Routing/model mocked; OA HTTP and rules real.")
    finally:
        for item in reversed(servers):
            stop_server(item)


if __name__ == "__main__":
    run()
