FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Latency knobs (ms) - tune to make load-test percentiles more/less spread out.
ENV AGENT_BASE_LATENCY_MS=40
ENV AGENT_JITTER_MS=60

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
