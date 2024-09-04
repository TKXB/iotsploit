import sqlite3
from datetime import datetime

# Connect to SQLite database (or create it if it doesn't exist)
conn = sqlite3.connect('devices.db')
cursor = conn.cursor()

# Create a table for storing device information
cursor.execute('''
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    status TEXT NOT NULL,
    type TEXT NOT NULL,
    creationTime TEXT NOT NULL
)
''')

# Define device information
devices = [
    {
        'name': 'Cracker',
        'path': '/dev/ttyUSB0',
        'status': 'active',
        'type': 'USB',
        'creationTime': '2024-08-23 17:34:21'
    },
    {
        'name': 'Device1',
        'path': '/dev/ttyUSB1',
        'status': 'inactive',
        'type': 'USB',
        'creationTime': '2024-08-24 10:15:30'
    },
    {
        'name': 'Device2',
        'path': '/dev/ttyUSB2',
        'status': 'active',
        'type': 'USB',
        'creationTime': '2024-08-24 11:45:00'
    },
    {
        'name': 'Device3',
        'path': '/dev/ttyUSB3',
        'status': 'inactive',
        'type': 'USB',
        'creationTime': '2024-08-24 12:00:00'
    },
    {
        'name': 'Device4',
        'path': '/dev/ttyUSB4',
        'status': 'active',
        'type': 'USB',
        'creationTime': '2024-08-24 13:30:00'
    },
    {
        'name': 'Device5',
        'path': '/dev/ttyUSB5',
        'status': 'inactive',
        'type': 'USB',
        'creationTime': '2024-08-24 14:45:00'
    },
    {
        'name': 'Device6',
        'path': '/dev/ttyUSB6',
        'status': 'active',
        'type': 'USB',
        'creationTime': '2024-08-24 15:00:00'
    },
    {
        'name': 'Device7',
        'path': '/dev/ttyUSB7',
        'status': 'inactive',
        'type': 'USB',
        'creationTime': '2024-08-24 16:30:00'
    },
    {
        'name': 'Device8',
        'path': '/dev/ttyUSB8',
        'status': 'active',
        'type': 'USB',
        'creationTime': '2024-08-24 17:45:00'
    },
    {
        'name': 'Device9',
        'path': '/dev/ttyUSB9',
        'status': 'inactive',
        'type': 'USB',
        'creationTime': '2024-08-24 18:00:00'
    },
    {
        'name': 'Device10',
        'path': '/dev/ttyUSB10',
        'status': 'active',
        'type': 'USB',
        'creationTime': '2024-08-24 19:30:00'
    }
]

# Insert devices into the table
for device in devices:
    cursor.execute('''
    INSERT INTO devices (name, path, status, type, creationTime)
    VALUES (:name, :path, :status, :type, :creationTime)
    ''', device)

# Commit the changes and close the connection
conn.commit()
conn.close()

print('Devices added successfully')
