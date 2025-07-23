# SAT Toolkit Docker Setup

This Docker setup provides a complete, containerized version of the SAT (Security Assessment Toolkit) that includes:

- **Python 3.10** - Backend API and core functionality
- **Poetry** - Python dependency management
- **Flutter 3.24.0** - Web-based user interface
- **Redis** - Caching and session management
- **Nginx** - Web server and reverse proxy
- **Ubuntu 22.04** - Base operating system

## 🚀 Quick Start

### Prerequisites

- Docker (version 20.10 or higher)
- Docker Compose (version 1.29 or higher)
- At least 4GB RAM available for Docker
- At least 10GB free disk space
- Project with `pyproject.toml` (Poetry configuration)

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
git clone <your-repo-url>
cd zeekr_sat_main-master

# Build and start the container
docker-compose up --build

# Or run in background
docker-compose up -d --build
```

### Option 2: Docker Build

```bash
# Build the image
docker build -t sat-toolkit .

# Run the container
docker run -d \
  --name sat-toolkit \
  -p 80:80 \
  -p 8888:8888 \
  -p 9999:9999 \
  -p 6379:6379 \
  sat-toolkit
```

## 🌐 Access Points

Once the container is running, you can access:

| Service | URL | Description |
|---------|-----|-------------|
| **Web UI** | http://localhost | Main Flutter web interface |
| **API** | http://localhost/api/ | Python backend API |
| **Admin** | http://localhost/admin/ | Django admin interface |
| **WebSocket** | ws://localhost/ws/ | Real-time communication |
| **Health Check** | http://localhost/health | Container health status |

### Direct Access (Development)

| Service | URL | Description |
|---------|-----|-------------|
| **Python API** | http://localhost:8888 | Direct backend access |
| **WebSocket** | ws://localhost:9999 | Direct WebSocket access |
| **Redis** | localhost:6379 | Direct Redis access |

## 🔑 Default Credentials

- **Django Admin**: `admin` / `admin123`

## 📊 Container Status

### Check if services are running

```bash
# View container logs
docker-compose logs -f

# Check specific service logs
docker-compose logs -f sat-toolkit

# Check container status
docker-compose ps

# Check health status
curl http://localhost/health
```

### Monitor services inside container

```bash
# Access container shell
docker exec -it sat-toolkit bash

# Check supervisor status
supervisorctl status

# Check individual service logs
tail -f /var/log/supervisor/django.log
tail -f /var/log/supervisor/nginx.log
tail -f /var/log/supervisor/redis.log
```

## 🛠️ Development Mode

For development, you can mount your local code into the container:

```yaml
# In docker-compose.yml, uncomment these lines:
volumes:
  - ./:/app
  - /app/ui/build  # Exclude build directory
```

Then rebuild:

```bash
docker-compose down
docker-compose up --build
```

## 🔧 Configuration

### Environment Variables

You can customize the container behavior using environment variables:

```bash
# In docker-compose.yml or docker run command
environment:
  - DEBUG=True                    # Enable Django debug mode
  - REDIS_URL=redis://redis:6379  # Redis connection URL
  - ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com
```

### Persistent Data

Data is automatically persisted in Docker volumes:

- `sat_data` - Redis data and application data
- `sat_logs` - Application logs
- `sat_uploads` - Uploaded files

### Custom Configuration

You can override configuration files by mounting them:

```yaml
volumes:
  - ./custom-nginx.conf:/etc/nginx/sites-available/default
  - ./custom-redis.conf:/etc/redis/redis.conf
```

## 🐛 Troubleshooting

### Container won't start

```bash
# Check build logs
docker-compose build --no-cache

# Check startup logs
docker-compose logs sat-toolkit

# Check system resources
docker system df
docker system prune  # Clean up if needed
```

### Flutter build fails

```bash
# Rebuild Flutter manually inside container
docker exec -it sat-toolkit bash
cd /app/ui
flutter clean
flutter pub get
flutter build web --release
```

### Python backend issues

```bash
# Check Django logs
docker exec -it sat-toolkit tail -f /var/log/supervisor/django.log

# Run Django commands manually
docker exec -it sat-toolkit python manage.py check
docker exec -it sat-toolkit python manage.py migrate

# Poetry-specific debugging
docker exec -it sat-toolkit poetry --version
docker exec -it sat-toolkit poetry show  # List installed packages
docker exec -it sat-toolkit poetry check  # Verify dependencies
```

### Redis connection issues

```bash
# Check Redis status
docker exec -it sat-toolkit redis-cli ping

# Check Redis logs
docker exec -it sat-toolkit tail -f /var/log/supervisor/redis.log
```

### Performance issues

```bash
# Check resource usage
docker stats sat-toolkit

# Check disk usage
docker exec -it sat-toolkit df -h

# Check memory usage
docker exec -it sat-toolkit free -h
```

## 🔄 Updates and Maintenance

### Update the container

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose up --build -d
```

### Backup data

```bash
# Backup volumes
docker run --rm -v sat_data:/data -v $(pwd):/backup alpine tar czf /backup/sat_data_backup.tar.gz -C /data .

# Backup database (if using external DB)
docker exec sat-toolkit python manage.py dumpdata > backup.json
```

### Clean up

```bash
# Stop and remove containers
docker-compose down

# Remove volumes (WARNING: This deletes all data)
docker-compose down -v

# Clean up Docker system
docker system prune -a
```

## 📈 Scaling and Production

### Production Deployment

For production use, consider:

1. **Use external database** (PostgreSQL)
2. **Use external Redis** cluster
3. **Configure SSL/HTTPS**
4. **Set up monitoring** (Prometheus, Grafana)
5. **Configure backup** strategy
6. **Use secrets management**

### Example production docker-compose.yml

```yaml
version: '3.8'
services:
  sat-toolkit:
    image: your-registry/sat-toolkit:latest
    environment:
      - DEBUG=False
      - DATABASE_URL=postgresql://user:pass@postgres:5432/sat_db
      - REDIS_URL=redis://redis:6379
      - SECRET_KEY=your-secret-key
    depends_on:
      - postgres
      - redis
    
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: sat_db
      POSTGRES_USER: sat_user
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
```

## 🆘 Support

If you encounter issues:

1. Check the logs: `docker-compose logs -f`
2. Verify system requirements
3. Check Docker and Docker Compose versions
4. Review the troubleshooting section above
5. Open an issue with detailed logs and system information

## 📝 Technical Details

### Container Architecture

```
┌─────────────────────────────────────┐
│            Nginx (Port 80)          │
│  ┌─────────────┐ ┌─────────────────┐ │
│  │ Flutter Web │ │  API Proxy      │ │
│  │   (Static)  │ │ (to Python)     │ │
│  └─────────────┘ └─────────────────┘ │
└─────────────────┬───────────────────┘
                  │
┌─────────────────┴───────────────────┐
│         Python Backend              │
│  ┌─────────────┐ ┌─────────────────┐ │
│  │   Django    │ │    Daphne       │ │
│  │ (Port 8888) │ │  (Port 9999)    │ │
│  └─────────────┘ └─────────────────┘ │
└─────────────────┬───────────────────┘
                  │
┌─────────────────┴───────────────────┐
│          Redis (Port 6379)          │
└─────────────────────────────────────┘
```

### Build Process

1. **Base System**: Ubuntu 22.04 with Python 3.10
2. **Flutter Installation**: Git clone and build Flutter 3.24.0
3. **Poetry Setup**: Install Poetry for dependency management
4. **Dependencies**: Install Python packages from pyproject.toml using Poetry
5. **Flutter Build**: Build web version of Flutter app
6. **Configuration**: Set up Nginx, Redis, Supervisor
7. **Services**: Start all services via Supervisor

### Resource Requirements

- **CPU**: 2+ cores recommended
- **RAM**: 4GB minimum, 8GB recommended
- **Disk**: 10GB minimum for image + data
- **Network**: Internet access for initial build 