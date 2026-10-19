import logging
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from openai import APIConnectionError, APIStatusError, APITimeoutError

from assistant.schemas import AskRequest, AskResponse
from assistant.service import KnowledgeUnavailable, ModelOutputError
from assistant.orchestrator import handle_question as answer_question
from assistant.oa_client import OAError

app = FastAPI(title="OA 智能助手", version="0.5.0")
logger = logging.getLogger("uvicorn.error")


@app.get("/health")
def health():
    return {"status": "ok", "service": "assistant"}


@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest):
    request_id = uuid4().hex[:12]
    try:
        result = answer_question(body.question)
    except APITimeoutError:
        status, code, message = 504, "model_timeout", "模型服务超时，请稍后重试。"
    except APIConnectionError:
        status, code, message = 503, "model_connection", "暂时无法连接模型服务。"
    except APIStatusError:
        status, code, message = 502, "model_api_error", "模型接口返回错误，请检查账号、模型配置与额度。"
    except ModelOutputError:
        status, code, message = 502, "invalid_model_output", "模型没有返回有效的结构化结果，请重试。"
    except KnowledgeUnavailable:
        status, code, message = 503, "knowledge_unavailable", "知识库暂不可用，请检查资料并重建索引。"
    except OAError as error:
        status, code = error.http_status, error.code
        message = {503: "暂时无法连接OA服务。", 504: "OA服务超时，请稍后重试。"}.get(status, "OA返回的数据或接口契约异常，请检查后端。")
    except RuntimeError:
        status, code, message = 503, "configuration_error", "服务配置不完整，请检查本地配置。"
    else:
        logger.info("request_id=%s status=%s reason=%s citations=%s", request_id,
                    result.status, result.reason, len(result.citations))
        return result.model_copy(update={"request_id": request_id})

    logger.warning("request_id=%s error=%s", request_id, code)
    raise HTTPException(status_code=status, detail={
        "code": code, "message": message, "request_id": request_id,
    })
