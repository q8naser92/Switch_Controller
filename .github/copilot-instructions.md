# GitHub Copilot Instructions for Switch_Controller

## Project Overview

This is a Flask-based web application that provides a user interface for controlling a Nintendo Switch via NXBT (Nintendo Switch Bluetooth toolkit). The application manages Bluetooth connections and executes programmed controller inputs on a Nintendo Switch console.

## Tech Stack

- **Language**: Python 3.11
- **Web Framework**: Flask
- **Deployment**: Raspberry Pi (ARM64) via systemd service
- **Dependencies**: NXBT, bluetoothctl, screen
- **CI/CD**: GitHub Actions with self-hosted runner

## Project Structure

```
Switch_Controller/
├── app.py              # Main Flask application with all API endpoints
├── templates/          # HTML templates for the web UI
│   └── index.html     # Main UI page
├── .github/
│   └── workflows/     # GitHub Actions workflows
│       ├── deploy.yml # Deployment to Raspberry Pi
│       ├── ai-change.yml
│       └── ai-chatops.yml
└── .gitignore
```

## Coding Standards

### Python Style
- Follow PEP 8 conventions
- Use type hints where appropriate (already used in some helper functions like `screen_exists(name: str) -> bool`)
- Maintain consistency with existing code style
- Use pathlib.Path for file operations (already established pattern)
- Use descriptive variable names

### Flask Patterns
- Use route decorators consistently (`@app.get()`, `@app.post()`)
- Return JSON responses using `jsonify()`
- Use `_json_nocache()` helper for responses that should not be cached
- Follow REST conventions for API endpoints

### Security
- Always validate and sanitize user inputs
- Prevent directory traversal attacks (already implemented in presets endpoints)
- Use shlex.quote() for shell command arguments
- Validate file paths are within expected directories

### Error Handling
- Return appropriate HTTP status codes (400 for bad requests, 404 for not found, 500 for server errors)
- Include descriptive error messages in JSON responses
- Log errors to API_LOG when appropriate

## Development Workflow

### Testing
- Test Flask endpoints manually via curl or the web UI
- Verify that screen sessions are created/stopped correctly
- Check log files are written properly
- Ensure file operations work as expected

### Building/Linting
- The project does not currently have automated linters or test suites
- Manual testing via the deployed service is the primary verification method
- Code review focuses on security, correctness, and consistency with existing patterns

### Deployment
- Deployment is automated via GitHub Actions when pushing to `main` branch
- Self-hosted runner on Raspberry Pi with specific sudoers rules
- Files are synced to `/opt/nxui` and the systemd service is restarted
- Health check verifies the service is running after deployment

## Key Considerations

### File Paths
- Most paths are hardcoded for the Raspberry Pi deployment environment:
  - `/root/init.txt` and `/root/loop.txt` for controller sequences
  - `/root/presets/` for saved presets
  - `/var/log/nxui/` for log files
  - `/opt/nxui/` for application files
  - `/root/.pyenv/versions/nxbt-3.11/bin/python` for Python interpreter

### Screen Sessions
- The app uses GNU screen to manage background processes
- Two session types: `nxui_bt` for bluetoothctl and `nxui_prog` for NXBT loop
- Always check if a session exists before attempting to start/stop it

### API Endpoints
The application provides RESTful endpoints for:
- Bluetooth management (`/bluetooth/*`)
- Program execution (`/program/*`)
- File operations (`/files/*`)
- Preset management (`/presets/*`)
- Health monitoring (`/health`)

## Common Tasks

### Adding New API Endpoints
1. Define route using `@app.get()` or `@app.post()`
2. Parse request data using `request.get_json()` or `request.args.get()`
3. Validate inputs thoroughly
4. Return JSON response using `jsonify()` or `_json_nocache()`
5. Include appropriate HTTP status codes

### Modifying File Operations
1. Always use pathlib.Path for file operations
2. Validate file paths to prevent directory traversal
3. Use `encoding="utf-8"` for text operations
4. Handle exceptions gracefully
5. Log errors to API_LOG

### Working with Screen Sessions
1. Use helper functions: `screen_exists()`, `screen_start()`, `screen_send()`, `screen_kill()`
2. Always check if a session exists before operations
3. Use proper shell escaping with `shlex.quote()`
4. Log operations to API_LOG

## Notes for AI Assistants

- This is a working production system deployed on a Raspberry Pi
- Make minimal, surgical changes to avoid breaking existing functionality
- Preserve the existing code style and patterns
- Security is critical - always validate inputs and prevent injection attacks
- The deployment environment has specific constraints (paths, permissions, dependencies)
- When in doubt, follow the patterns already established in the codebase
