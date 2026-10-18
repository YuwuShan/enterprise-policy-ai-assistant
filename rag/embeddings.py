import numpy as np

DIMENSIONS = 1024
BATCH_SIZE = 10


def normalize(vectors) -> np.ndarray:
    array = np.asarray(vectors, dtype=np.float32)
    if array.ndim != 2 or not np.isfinite(array).all():
        raise ValueError("向量必须是二维数组，且只能包含有限数值")
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    if (norms == 0).any() or not np.isfinite(norms).all():
        raise ValueError("向量长度不能为零或非有限值")
    return array / norms


def embed_texts(texts: list[str], model: str) -> np.ndarray:
    from model_client import create_client

    if not texts or any(not text.strip() for text in texts):
        raise ValueError("待向量化的文本不能为空")

    vectors = []
    with create_client() as client:
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start:start + BATCH_SIZE]
            response = client.embeddings.create(
                model=model,
                input=batch,
                dimensions=DIMENSIONS,
                encoding_format="float",
            )
            ordered = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in ordered] != list(range(len(batch))):
                raise ValueError("向量接口返回的数量或序号异常")
            vectors.extend(item.embedding for item in ordered)
            print(f"已向量化 {min(start + BATCH_SIZE, len(texts))}/{len(texts)} 条")

    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.shape != (len(texts), DIMENSIONS):
        raise ValueError(f"向量形状异常：{matrix.shape}")
    return normalize(matrix)
