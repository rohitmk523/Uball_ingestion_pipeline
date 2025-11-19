# Basketball Video Processing Pipeline - Docker Image
# For EC2 deployment (testing/simulation)

FROM nvidia/cuda:11.8.0-base-ubuntu22.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    python3-venv \
    ffmpeg \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY run.sh .
COPY config.json .

# Create necessary directories
RUN mkdir -p logs temp/segments temp/compressed temp/thumbnails

# Create non-root user
RUN useradd -m -u 1000 basketball && \
    chown -R basketball:basketball /app

USER basketball

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

