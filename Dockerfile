FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN adduser --disabled-password --gecos "" botuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY README.md .
COPY btc_alpaca_15m_validation.py .
COPY backtest_tradingview_strategies.py .
COPY btc_first_principles_strategy.py .
COPY btc_simple_best_strategy.py .

RUN mkdir -p /app/state && chown -R botuser:botuser /app

USER botuser

CMD ["python", "-m", "app.bot"]

