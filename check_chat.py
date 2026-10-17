from model_client import create_client, required_env


def main():
    model = required_env("CHAT_MODEL")

    with create_client() as client:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "你是一名讲解清楚的 Python 学习助手。",
                },
                {
                    "role": "user",
                    "content": "请用一句话解释什么是 HTTP API。",
                },
            ],
        )

    answer = response.choices[0].message.content

    if not answer or not answer.strip():
        raise RuntimeError("请求已返回，但没有获得非空回答")

    print("聊天模型调用成功")
    print("模型：", model)
    print("回答：", answer)


if __name__ == "__main__":
    main()