# IotSploit

## Initial Setup

Follow these steps to set up the IotSploit project on your local machine.

### 1. Clone the Repository and Switch to the Development Branch

```bash
git fetch
git checkout -b dev origin/dev
```

### 2. Set Up Redis

Ensure you have Docker installed, then run the following commands:

```bash
docker pull redis
docker run --name sat-redis -p 6379:6379 -d redis:latest
```

### 3. Install and Configure Poetry

Poetry is used for dependency management. Install and configure it with:

```bash
pip install poetry
pip install poetry-plugin-shell
poetry lock        # This may take 10-20 minutes
poetry install     # This may take 10-20 minutes
poetry shell
```

### 4. Initialize the Django Database

Run the following commands to set up the database:

```bash
python manage.py makemigrations
python manage.py makemigrations sat_toolkit
python manage.py migrate
```

### 5. Start the Application

Launch the application with:

```bash
python console.py
```

## Using the IoTSploit Shell

Once the application is running, you can interact with it using the IoTSploit Shell. Below are some of the key commands available:

### System Commands

- **exploit**: Execute all plugins in the IotSploit System.
- **exit**: Exit the IoTSploit Shell.

### Device Commands

- **device_info**: Show Zeekr SAT Device Info.
- **list_devices**: List all devices stored in the database.
- **list_device_drivers**: List all available device plugins.

### Network Commands

- **connect_lab_wifi**: Connect to Zeekr Lab WiFi.

### Django Commands

- **runserver**: Start Django development server, Daphne WebSocket server, and Celery worker in the background.
- **stop_server**: Stop Django development server, Daphne WebSocket server, and Celery worker.

### Plugin Commands

- **list_plugins**: List all available plugins.
- **execute_plugin**: Execute a specific plugin.
- **flash_plugins**: Refresh and reload all plugins from the plugins directory.
- **create_group**: Create a plugin group and add selected plugins to it.
- **execute_group**: Execute plugins in a selected group.
- **list_groups**: List all available plugin groups.

### Target Commands

- **list_targets**: List all targets stored in the database.
- **target_select**: Select a target from available targets.
- **edit_target**: Edit an existing target in the database.

### Test Commands

- **test_select**: Select Test Project.
- **run_test**: Start Test Project.
- **quick_test**: Run Test Project quickly.

### Help

- **help**: List available commands or get detailed help for a specific command.

### Additional Information

- **set_log_level**: Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
- **ls**: List directory contents.
- **lsusb**: List USB devices.

For more detailed information on each command, you can type `help <command>` within the IoTSploit Shell.
