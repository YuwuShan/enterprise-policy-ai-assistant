import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# 按文件位置查找配置，不依赖终端当前所在目录。
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(ENV_PATH)


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(f"缺少配置：{name}，请检查 .env 文件")

    return value


def create_client() -> OpenAI:
    api_key = required_env("DASHSCOPE_API_KEY")
    base_url = required_env("DASHSCOPE_BASE_URL")

    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=30.0,
        max_retries=0,
    )