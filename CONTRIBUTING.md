# Contributing to IotSploit

Thank you for your interest in contributing to IotSploit! This document provides guidelines and instructions for contributing to this project.

## Getting Started

### Prerequisites

- Python 3.9 or higher
- Docker (for Redis)
- Poetry for dependency management

### Development Setup

1. Fork the repository and clone your fork
   ```bash
   git clone https://github.com/your-username/your-fork.git
   cd your-fork
   ```

2. Set up the development environment
   ```bash
   # Configure Redis
   docker pull redis
   docker run --name sat-redis -p 6379:6379 -d redis:latest

   # Install dependencies
   pip install poetry
   pip install poetry-plugin-shell
   poetry lock
   poetry install
   poetry shell

   # Initialize the database
   python manage.py makemigrations
   python manage.py makemigrations sat_toolkit
   python manage.py migrate
   ```

3. Start the application
   ```bash
   python console.py
   ```

## Development Workflow

1. Create a new branch for your feature or bugfix
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and test thoroughly

3. Commit your changes with clear, descriptive commit messages
   ```bash
   git commit -m "Add feature: description of changes"
   ```

4. Push your branch to your forked repository
   ```bash
   git push origin feature/your-feature-name
   ```

5. Create a pull request against the main repository

## Adding Plugins

IotSploit supports a plugin architecture. New plugins should be added to the `plugins/` directory following these guidelines:

1. Create a new directory for your plugin in the appropriate subdirectory:
   - `plugins/devices/` for device drivers
   - `plugins/exploits/` for exploit modules

2. Include necessary setup files and documentation

3. Test your plugin thoroughly before submission

## Code Style Guidelines

- Follow PEP 8 style guidelines for Python code
- Use meaningful variable and function names
- Include docstrings for modules, classes, and functions
- Write clear comments for complex logic

## Testing

- Write unit tests for new functionality
- Ensure all tests pass before submitting a pull request
- Include test cases that cover edge cases and error conditions

## Documentation

- Update documentation for any changes to existing features
- Document new features thoroughly
- Update the README.md if necessary

## Pull Request Process

1. Ensure your code follows the style guidelines
2. Update documentation as necessary
3. Make sure all tests pass
4. Your pull request will be reviewed by maintainers
5. Address any feedback or requested changes

## Reporting Issues

If you find a bug or want to request a new feature:

1. Check existing issues to avoid duplicates
2. Use the issue templates to provide all necessary information
3. Be clear and descriptive about the problem or feature request

## Community

- Be respectful and inclusive in all interactions
- Help others when possible
- Share knowledge and resources

Thank you for contributing to IotSploit! 