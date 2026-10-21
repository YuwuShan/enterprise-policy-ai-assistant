FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

RUN useradd --uid 10001 --create-home app \
    && mkdir -p /app/data/policies /app/data/index \
    && chown -R app:app /app

COPY --chown=app:app assistant ./assistant
COPY --chown=app:app oa ./oa
COPY --chown=app:app rag ./rag
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app deploy/container_start.py deploy/persistence_probe.py ./deploy/
COPY --chown=app:app model_client.py check_day4.py check_day5.py ./

USER app
CMD ["python", "deploy/container_start.py", "assistant"]
