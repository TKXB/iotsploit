# SAT Toolkit Docker Image
# Based on Ubuntu 22.04 with Python 3.10
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
    # Web server dependencies
    nginx \
    # Network tools
    iproute2 \
    net-tools \
    iputils-ping \
    nmap \
    util-linux \
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

# Native headers required by the locked Cairo, D-Bus, and GObject bindings.
RUN apt-get update && apt-get install -y \
    libcairo2-dev \
    libdbus-1-dev \
    libgirepository1.0-dev \
    pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip3 install poetry==1.8.3

# Configure Poetry
RUN poetry config virtualenvs.create false \
    && poetry config cache-dir /opt/poetry

# Build the checked-out tree supplied as the Docker build context.
COPY . /app/

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

# Create service accounts, immutable launchers, and writable service paths.
RUN groupadd --system iotsploit \
    && usermod --append --groups iotsploit www-data \
    && install -D -o root -g root -m 0755 /app/iotsploit-priv/privd/iotsploit-privd /usr/local/libexec/iotsploit-privd \
    && install -D -o root -g root -m 0755 /app/docker/run-with-capability.sh /usr/local/libexec/iotsploit-run-cap \
    && mkdir -p /app/data /app/logs/nginx /app/uploads /run/iotsploit-nginx \
        /var/cache/iotsploit-nginx/client /var/cache/iotsploit-nginx/proxy \
        /var/cache/iotsploit-nginx/fastcgi /var/cache/iotsploit-nginx/uwsgi \
        /var/cache/iotsploit-nginx/scgi /var/log/supervisor \
    && chmod -R 755 /app \
    && chown -R www-data:www-data /app/data /app/logs /app/uploads /app/static \
        /run/iotsploit-nginx /var/cache/iotsploit-nginx

# Copy configuration files from build context (local files)
COPY docker/nginx.conf /etc/nginx/sites-available/default
COPY docker/nginx-main.conf /etc/nginx/nginx.conf
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/start.sh /app/start.sh

# Make start script executable
RUN chmod +x /app/start.sh

# Expose ports
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:80 || exit 1

# Set working directory back to app
WORKDIR /app

# Start all services
CMD ["/app/start.sh"]
