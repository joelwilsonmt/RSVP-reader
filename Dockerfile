FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ templates/
COPY static/ static/

ENV PORT=5002
EXPOSE 5002

# One worker keeps the shared SQLite connection and caches in-process; threads handle concurrency.
CMD ["sh", "-c", "exec gunicorn -w 1 --threads 8 --timeout 300 -b 0.0.0.0:${PORT} app:app"]
