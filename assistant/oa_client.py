"""Step 2: call fixed OA endpoints over HTTP, with bounded time and output validation."""
import json
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from pydantic import ValidationError

# Reuse the shared API contracts; do not call oa.main functions directly.
from oa.schemas import ApprovalResponse, BudgetResponse, SuppliersResponse

ENDPOINTS = {
    "query_budget": ("GET", "/budgets", BudgetResponse),
    "query_suppliers": ("GET", "/suppliers", SuppliersResponse),
    "get_approval_chain": ("POST", "/approval-chain", ApprovalResponse),
}


class OAError(RuntimeError):
    def __init__(self, code, http_status):
        super().__init__(code)
        self.code, self.http_status = code, http_status


class BudgetNotFound(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def call_oa(name, arguments):
    method, path, schema = ENDPOINTS[name]
    base = os.getenv("OA_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.query or parts.fragment or parts.path or parts.username:
        raise RuntimeError("OA_BASE_URL应为受信任的OA服务地址，不包含路径或账号")
    data = None
    url = base + path
    if method == "GET":
        if arguments:
            url += "?" + urlencode(arguments)
    else:
        data = json.dumps(arguments, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    # Directly access the configured internal OA service; do not use a system proxy.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=5) as response:
            raw = response.read(1_000_001)
    except HTTPError as error:
        status = error.code
        error.close()
        if status == 404 and name == "query_budget":
            raise BudgetNotFound from error
        # Local validation already passed; OA rejection indicates a contract/config mismatch.
        raise OAError("oa_rejected_arguments" if status == 422 else "oa_http_error", 502) from error
    except (TimeoutError, socket.timeout) as error:
        raise OAError("oa_timeout", 504) from error
    except URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise OAError("oa_timeout", 504) from error
        raise OAError("oa_unavailable", 503) from error
    except OSError as error:
        raise OAError("oa_unavailable", 503) from error
    try:
        if len(raw) > 1_000_000:
            raise ValueError("OA响应过大")
        return schema.model_validate_json(raw).model_dump(mode="json")
    except (ValidationError, ValueError) as error:
        raise OAError("oa_bad_response", 502) from error
