# SAT Toolkit Docker Image
# Based on Ubuntu 22.04 with Python 3.10 and Redis
FROM ubuntu:22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Poetry configuration
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/opt/poetry \
    POETRY_HOME="/opt/poetry"

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Basic tools
    curl \
    wget \
    git \
    unzip \
    xz-utils \
    zip \
    # Python and development tools
    python3.10 \
    python3.10-dev \
    python3-pip \
    python3.10-venv \
    # Redis
    redis-server \
    redis-tools \
    # Web server dependencies
    nginx \
    # Network tools
    net-tools \
    iputils-ping \
    # Build tools
    build-essential \
    libffi-dev \
    libssl-dev \
    # Process management
    supervisor \
    # JSON parsing tools
    jq \
    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create symbolic link for python
RUN ln -s /usr/bin/python3.10 /usr/bin/python

# Install Poetry
RUN pip3 install poetry==1.8.3

# Configure Poetry
RUN poetry config virtualenvs.create false \
    && poetry config cache-dir /opt/poetry

# Clone the IoTSploit source code from GitHub
RUN git clone https://github.com/TKXB/iotsploit.git /tmp/iotsploit \
    && cp -r /tmp/iotsploit/* /app/ \
    && cp -r /tmp/iotsploit/.* /app/ 2>/dev/null || true \
    && rm -rf /tmp/iotsploit

# Install all Python dependencies with Poetry (main + dev + plugins)
RUN poetry install

# Set up Django settings (container default)
ENV DJANGO_SETTINGS_MODULE=iotsploit_django.settings.prod

# Download and extract pre-built Flutter web application to static/web directory
RUN mkdir -p /app/static/web \
    && cd /tmp \
    && echo "Fetching latest version info..." \
    && LATEST_VERSION=$(curl -s https://www.iotsploit.org/download.html | grep -oP 'iotsploit-ui-v\K[0-9]+\.[0-9]+\.[0-9]+' | head -1) \
    && echo "Latest version detected: v${LATEST_VERSION}" \
    && WEB_URL="https://www.iotsploit.org/downloads/iotsploit-ui-v${LATEST_VERSION}-web.zip" \
    && echo "Downloading from: ${WEB_URL}" \
    && wget --no-check-certificate "${WEB_URL}" -O iotsploit-ui-web.zip \
    && unzip -q iotsploit-ui-web.zip -d /app/static/web/ \
    && rm iotsploit-ui-web.zip \
    && echo "Flutter web application downloaded and extracted to static/web directory successfully"

# Create necessary directories and set permissions
RUN mkdir -p /app/logs /app/uploads /var/log/nginx \
    && chmod -R 755 /app \
    && chown -R www-data:www-data /app/static

# Copy configuration files from build context (local files)
COPY docker/nginx.conf /etc/nginx/sites-available/default
COPY docker/redis.conf /etc/redis/redis.conf  
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/start.sh /app/start.sh

# Make start script executable
RUN chmod +x /app/start.sh

# Expose ports
EXPOSE 80 8888 9999 6379

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:80 || exit 1

# Set working directory back to app
WORKDIR /app

# Start all services
CMD ["/app/start.sh"] 