FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY queue_server ./queue_server

ENV PYTHONPATH=/app

CMD ["python", "-m", "queue_server.main"]
