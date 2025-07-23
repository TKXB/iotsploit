# SAT Toolkit Docker + Poetry Integration Guide

This guide explains how the SAT Toolkit Docker setup integrates with Poetry for Python dependency management.

## 🎯 **Poetry Integration Benefits**

### **Before (pip + requirements.txt)**
```bash
# Manual dependency management
pip freeze > requirements.txt
pip install -r requirements.txt
# No lock file, potential version conflicts
```

### **After (Poetry)**
```bash
# Automatic dependency management
poetry add package-name
poetry install
# poetry.lock ensures reproducible builds
```

## 📁 **File Structure**

```
zeekr_sat_main-master/
├── pyproject.toml           # Poetry configuration (replaces requirements.txt)
├── poetry.lock              # Lock file for reproducible builds
├── Dockerfile               # Poetry-optimized Dockerfile
├── docker-compose.yml       # Container orchestration
└── docker/                  # Configuration files
```

## 🏗️ **Docker Build Strategy**

The Dockerfile uses an optimized approach that balances simplicity with performance:

```dockerfile
# Copy Poetry files first (better Docker layer caching)
COPY pyproject.toml poetry.lock* /app/

# Install main dependencies first
RUN poetry install --only=main --no-dev

# Copy project code
COPY . /app/

# Install all dependencies including dev/plugins
RUN poetry install
```

**Benefits:**
- ✅ **Layer Caching**: Dependencies cached separately from code changes
- ✅ **Two-Stage Install**: Main deps first, then dev/plugins
- ✅ **Simple**: Single Dockerfile, easy to understand
- ✅ **Optimized**: Faster rebuilds when only code changes

## 🔧 **Configuration Details**

### **Poetry Environment Variables**
```dockerfile
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/opt/poetry \
    POETRY_HOME="/opt/poetry"
```

### **Poetry Configuration Commands**
```dockerfile
RUN poetry config virtualenvs.create false \
    && poetry config cache-dir /opt/poetry
```

## 🚀 **Usage Examples**

### **Development Build**
```bash
# Standard build for development
docker-compose up --build
```

### **Production Build**
```bash
# Build for production (same command)
docker-compose up --build -d
```

### **Managing Dependencies**
```bash
# Add new dependency
poetry add requests

# Add development dependency
poetry add --group dev pytest

# Update dependencies
poetry update

# Rebuild container with new dependencies
docker-compose build --no-cache
```

## 🐛 **Troubleshooting Poetry Issues**

### **Poetry Installation Fails**
```bash
# Check Poetry version in container
docker exec -it sat-toolkit poetry --version

# Reinstall Poetry
docker exec -it sat-toolkit pip install poetry==1.8.3
```

### **Dependency Conflicts**
```bash
# Check dependency tree
docker exec -it sat-toolkit poetry show --tree

# Verify lock file
docker exec -it sat-toolkit poetry check

# Clear cache and reinstall
docker exec -it sat-toolkit poetry cache clear pypi --all
docker exec -it sat-toolkit poetry install
```

### **Plugin Dependencies Not Found**
```bash
# Check if dev dependencies are installed
docker exec -it sat-toolkit poetry show --only=dev

# Install all dependencies including dev/plugins
docker exec -it sat-toolkit poetry install
```

## 📊 **Performance Benefits**

| Aspect | Before (pip) | After (Poetry) |
|--------|-------------|----------------|
| **Dependency Management** | Manual | Automatic |
| **Build Reproducibility** | Poor | Excellent |
| **Cache Efficiency** | Poor | Good |
| **Plugin Support** | Limited | Full |
| **Lock File** | None | poetry.lock |

## 🎯 **Best Practices**

### **1. Use poetry.lock**
```bash
# Always commit poetry.lock
git add poetry.lock
git commit -m "Update dependencies"
```

### **2. Separate Dependencies**
```toml
# pyproject.toml
[tool.poetry.dependencies]
python = "^3.10"
django = "^4.2.14"

[tool.poetry.group.dev.dependencies]
pytest = "^7.0.0"
black = "^23.0.0"

[tool.poetry.group.plugins.dependencies]
# Local plugin dependencies
flood_attack = {path = "plugins/exploits/flood_attack", develop = true}
```

### **3. Docker Layer Optimization**
```dockerfile
# Copy Poetry files first (better caching)
COPY pyproject.toml poetry.lock* ./
RUN poetry install --only=main

# Copy code later
COPY . .
RUN poetry install  # Only installs remaining dependencies
```

### **4. Environment-Specific Installs**
```dockerfile
# Production: only main dependencies
RUN poetry install --only=main --no-dev

# Development: all dependencies
RUN poetry install

# Testing: main + test dependencies
RUN poetry install --with=test
```

## 🔄 **Migration Guide**

### **From requirements.txt to Poetry**

1. **Generate pyproject.toml from requirements.txt**:
   ```bash
   poetry init
   # Follow prompts and add dependencies
   ```

2. **Update Dockerfile**:
   ```dockerfile
   # OLD
   COPY requirements.txt /app/
   RUN pip install -r requirements.txt
   
   # NEW
   COPY pyproject.toml poetry.lock* /app/
   RUN poetry install
   ```

3. **Update .dockerignore**:
   ```
   # Remove
   requirements.txt
   
   # Keep
   pyproject.toml
   poetry.lock
   ```

## 🎯 **Next Steps**

1. Choose appropriate Dockerfile based on your needs
2. Test the build: `./build-docker.sh`
3. Monitor build times and optimize as needed
4. Consider using the optimized multi-stage build for production

This Poetry integration provides better dependency management, reproducible builds, and improved Docker layer caching for your SAT Toolkit project! 🚀 