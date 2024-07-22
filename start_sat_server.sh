#!/bin/bash
pkill -f 'sudo python manage.py runserver 0.0.0.0:8000'
mkdir -p sat_logs
python manage.py runserver 0.0.0.0:8000 > sat_logs/sat_ui.log 2>&1

#pkill -f /usr/lib/chromium-browser/chromium-browser
#chromium-browser --start-fullscreen --app=http://127.0.0.1:8000/sat_ui/index.html

