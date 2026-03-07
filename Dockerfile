FROM python:3.11-slim

# System dependencies for OpenCV + EasyOCR
RUN apt-get update && apt-get install -y \
    libglib2.0-0 libsm6 libxext6 libxrender-dev \
    libgomp1 libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Install without CUDA (CPU-only, smaller image)
RUN pip install --no-cache-dir \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Create required directories
RUN mkdir -p web/static/snapshots web/static/uploads config

EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
  CMD curl -f http://localhost:5000/health || exit 1

CMD ["gunicorn", "server:app", "--workers", "1", "--threads", "4", \
     "--timeout", "120", "--bind", "0.0.0.0:5000"]
