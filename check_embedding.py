from model_client import create_client, required_env


def main():
    model = required_env("EMBEDDING_MODEL")
    text = "采购金额达到两万元时，需要总经理审批。"

    with create_client() as client:
        response = client.embeddings.create(
            model=model,
            input=[text],
            dimensions=1024,
            encoding_format="float",
        )

    vector = response.data[0].embedding

    if not isinstance(vector, list) or len(vector) != 1024:
        raise RuntimeError("没有获得预期的 1024 维向量")

    print("向量模型调用成功")
    print("模型：", model)
    print("向量维度：", len(vector))
    print("前 5 个数值：", vector[:5])


if __name__ == "__main__":
    main()