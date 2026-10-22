#!/bin/bash
set -e

echo "🚀 Starting SAT Toolkit Docker Container..."

RUN_APP="/usr/local/libexec/iotsploit-run-cap app"

for path in /app/data /app/logs /app/uploads /app/static /run/iotsploit-nginx /var/cache/iotsploit-nginx; do
    if ! $RUN_APP test -w "$path"; then
        echo "❌ $path must be writable by www-data" >&2
        exit 1
    fi
done

# Initialize Django database (if needed)
echo "📊 Initializing Django database..."
cd /app
$RUN_APP python manage.py collectstatic --noinput --clear || echo "⚠️  Static files collection failed (continuing...)"
echo "📊 Running Django migrations..."
$RUN_APP python manage.py migrate --noinput

# NEW: Ensure database file is writable by the Django (www-data) user
if [ -f "/app/data/db.sqlite3" ] && ! $RUN_APP test -w /app/data/db.sqlite3; then
    echo "❌ /app/data/db.sqlite3 must be writable by www-data" >&2
    exit 1
fi

# Run console.py initialization and exit immediately
echo "🔧 Running console.py initialization..."
echo "exit" | $RUN_APP python /app/console.py || echo "⚠️ Console.py initialization failed (continuing...)"
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

# Start supervisor to manage all services
echo "🎯 Starting all services with Supervisor..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
