#!/bin/bash
set -e

echo "🚀 Starting SAT Toolkit Docker Container..."

# Create necessary directories
mkdir -p /app/logs
mkdir -p /app/uploads
mkdir -p /app/static
mkdir -p /var/log/supervisor

# Set proper permissions
chown -R www-data:www-data /app/logs
chown -R www-data:www-data /app/uploads
chown -R www-data:www-data /app/static

# Initialize Django database (if needed)
echo "📊 Initializing Django database..."
cd /app
python manage.py collectstatic --noinput --clear || echo "⚠️  Static files collection failed (continuing...)"
echo "📊 Running Django migrations..."
python manage.py makemigrations || echo "⚠️  makemigrations failed (continuing...)"
python manage.py migrate || echo "⚠️  Database migration failed (continuing...)"

# NEW: Ensure database file is writable by the Django (www-data) user
if [ -f "/app/data/db.sqlite3" ]; then
    chown www-data:www-data /app/data/db.sqlite3
    chmod 664 /app/data/db.sqlite3
fi

# Create superuser if it doesn't exist
echo "👤 Creating Django superuser..."
python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@sat-toolkit.com', 'admin123')
    print('Superuser created: admin/admin123')
else:
    print('Superuser already exists')
EOF

# Run console.py initialization and exit immediately
echo "🔧 Running console.py initialization..."
echo "exit" | python /app/console.py || echo "⚠️ Console.py initialization failed (continuing...)"
echo "✅ Console.py initialization completed!"

# Test Flutter web build
echo "🧪 Testing Flutter web build..."
if [ ! -f "/app/static/web/index.html" ]; then
    echo "❌ Flutter web build not found in static/web directory!"
    echo "⚠️  Expected to find Flutter web files in /app/static/web/"
    ls -la /app/static/web/ || echo "Static/web directory not found"
else
    echo "✅ Flutter web build found in static/web directory"
fi

# Test Nginx configuration
echo "🌐 Testing Nginx configuration..."
nginx -t || {
    echo "❌ Nginx configuration test failed!"
    exit 1
}

# Display system information
echo "📋 System Information:"
echo "  - Python version: $(python --version)"
echo "  - Flutter version: $(flutter --version | head -1)"
echo "  - Nginx version: $(nginx -v 2>&1)"
echo "  - Container hostname: $(hostname)"
echo "  - Container IP: $(hostname -I | awk '{print $1}')"

# Display service information
echo "🔗 Service URLs:"
echo "  - Web UI: http://localhost (port 80)"
echo "  - Python API: http://localhost/api/"
echo "  - Django Admin: http://localhost/admin/"
echo "  - WebSocket: ws://localhost/ws/"
echo "  - Health Check: http://localhost/health"

# Display credentials
echo "🔑 Default Credentials:"
echo "  - Django Admin: admin / admin123"

# Start supervisor to manage all services
echo "🎯 Starting all services with Supervisor..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
