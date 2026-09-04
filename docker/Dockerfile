FROM python:3.11-slim-bookworm

# Build deps needed to compile llama-cpp-python from source on arm64/Pi
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code and modules
COPY . .
RUN chmod +x chat.sh

# Model is mounted at runtime, not baked in
ENV MODEL_PATH=/models/qwen2.5-0.5b-instruct-q4_k_m.gguf
ENV PORT=8000

EXPOSE 8000

CMD ["python3", "ui_cli.py"]
