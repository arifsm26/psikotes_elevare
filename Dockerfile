# backend/Dockerfile
FROM python:3.9-slim-bullseye
# --- TAMBAHKAN BLOK INI ---
# Install build dependencies required for mysqlclient
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*
# ---------------------------

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Ganti port jika Anda mau, tapi 8000 adalah default yang baik untuk internal container
# CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
CMD ["gunicorn", "-w", "5", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:8000"]
