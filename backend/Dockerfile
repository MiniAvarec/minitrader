FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/code

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY . /code
RUN pip install --upgrade pip && pip install -e . \
    # mt5linux client only (no deps: it declares the Windows-only MetaTrader5
    # wheel which can't install on Linux — the terminal lives in mt5gateway).
    && pip install --no-deps "mt5linux>=0.1.9"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
