FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app


FROM base AS api

COPY business/api/requirements.txt business/api/requirements.txt
COPY ml/requirements.txt ml/requirements-inference.txt ml/
RUN python -m pip install --no-cache-dir -r business/api/requirements.txt

COPY weather_contract.py .
COPY business/ business/
COPY data/__init__.py data/model_artifacts.py data/datasets.py data/
COPY data/processed/ data/processed/
COPY ml/__init__.py ml/features.py ml/
COPY ml/training/ ml/training/
COPY --chown=10001:10001 artifacts/ artifacts/
RUN mkdir /app/logs && chown 10001:10001 /app/logs

USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "business.api:app", "--host", "0.0.0.0", "--port", "8000"]


FROM base AS bot

COPY presentation/telegram_bot/requirements.txt presentation/telegram_bot/requirements.txt
RUN python -m pip install --no-cache-dir -r presentation/telegram_bot/requirements.txt

COPY weather_contract.py .
COPY presentation/weather_input.py presentation/
COPY presentation/telegram_bot/ presentation/telegram_bot/

USER 10001:10001
CMD ["python", "-m", "presentation.telegram_bot"]
