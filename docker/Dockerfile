# Basketball Video Pipeline Docker Container
# ARM64 compatible for Jetson Orin development/testing

FROM ubuntu:22.04

# Set non-interactive frontend for apt
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    wget \
    unzip \
    libmagic1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Create virtual environment and install Python dependencies
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application source code
COPY src/ ./src/
COPY .env.template .env

# Create necessary directories
RUN mkdir -p /app/recordings /app/logs /var/log

# Set environment variables
ENV PYTHONPATH="/app/src"
ENV FLASK_APP="src/web_ui.py"

# Create non-root user for security
RUN useradd -m -u 1000 basketball && \
    chown -R basketball:basketball /app /var/log

USER basketball

# Expose web interface port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/status || exit 1

# Default command - run web interface
CMD ["python3", "src/web_ui.py"]