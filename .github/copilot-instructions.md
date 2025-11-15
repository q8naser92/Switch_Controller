# GitHub Copilot Instructions for Switch_Controller

## Project Overview

This is a Flask-based web application that provides a user interface for controlling a Nintendo Switch via NXBT (Nintendo Switch Bluetooth toolkit). The application manages Bluetooth connections and executes programmed controller inputs on a Nintendo Switch console.

## Tech Stack

- **Language**: Python 3.11
- **Web Framework**: Flask
- **Deployment**: Raspberry Pi (ARM64) via systemd service
- **Dependencies**: 
  - NXBT (Nintendo Switch Bluetooth toolkit) - vendored in `src/nxbt/`
  - bluetoothctl for Bluetooth management
  - screen for process management
  - netifaces (optional) for network interface detection
- **CI/CD**: GitHub Actions with self-hosted runner

## Project Structure

```
Switch_Controller/
├── gui/                # Web UI application
│   ├── app.py         # Main Flask application with all API endpoints
│   └── templates/     # HTML templates for the web UI
│       └── index.html # Main UI page
├── config/            # Configuration files for controller sequences
│   ├── init.txt      # Initialization sequence commands
│   └── loop.txt      # Loop sequence commands
│   # (presets/ directory created at runtime in deployment location)
├── scripts/           # Utility scripts
│   └── nxbt_loop.py  # NXBT controller loop engine
├── src/              # Vendored dependencies
│   └── nxbt/         # NXBT (Nintendo Switch Bluetooth toolkit) source
├── .github/
│   ├── copilot-instructions.md  # This file
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
- Files are synced to `/opt/nxbt/` (all application code: gui/, scripts/, config/, src/)
- The systemd service `nxbt-gui` is restarted after deployment
- Health check verifies the service is running after deployment at port 8080

## Key Considerations

### File Paths
- Most paths are hardcoded for the Raspberry Pi deployment environment:
  - `/opt/nxbt/config/init.txt` and `/opt/nxbt/config/loop.txt` for controller sequences
  - `/opt/nxbt/config/presets/` for saved presets
  - `/var/log/nxui/` for log files
  - `/opt/nxbt/` for application files (gui/, scripts/, config/)
  - `/opt/pyenv/versions/nxbt-env/bin/python` for Python interpreter
  - `/opt/nxbt/scripts/nxbt_loop.py` for the NXBT loop engine
  - `/tmp/nxbt_cmd` for the FIFO pipe for external control

### Screen Sessions
- The app uses GNU screen to manage background processes
- Two session types: `nxui_bt` for bluetoothctl and `nxui_prog` for NXBT loop
- Always check if a session exists before attempting to start/stop it

### Configuration Files
The `config/` directory contains controller sequence files:
- `init.txt`: Initialization sequence run once when starting in mode A or C
- `loop.txt`: Looping sequence run repeatedly in modes A and B
- `presets/`: Directory for saving and loading named preset configurations
- Each file contains NXBT macro commands, one per line (comments start with `#`)
- Macro examples: `A 0.3s`, `B 0.5s`, `L_STICK@+000+100 1s`

### API Endpoints
The application provides RESTful endpoints for:
- Bluetooth management (`/bluetooth/*`)
- Program execution (`/program/*`)
- File operations (`/files/*`)
- Preset management (`/presets/*`)
- Service management (`/service/*`)
- Health monitoring (`/health`)

### NXBT Loop Engine
The `scripts/nxbt_loop.py` file is a standalone Python script that:
- Creates a virtual Nintendo Switch Pro Controller using NXBT
- Reads controller sequences from `/opt/nxbt/config/init.txt` and `/opt/nxbt/config/loop.txt`
- Supports multiple operating modes via FIFO pipe (`/tmp/nxbt_cmd`):
  - `manual`: Wait for commands via FIFO
  - `mode a`: Run init.txt once, then loop loop.txt repeatedly
  - `mode b`: Loop loop.txt repeatedly (no init)
  - `mode c`: Run init.txt once, then return to manual
- Accepts commands via stdin or FIFO: `mode`, `send`, `status`, `quit`
- Runs as a background process managed by GNU screen sessions

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

### Working with NXBT Loop Engine
1. The loop engine (`scripts/nxbt_loop.py`) is controlled via FIFO pipe at `/tmp/nxbt_cmd`
2. Send commands using `send_to_fifo()` helper function in Flask app
3. Commands are newline-terminated strings written to the FIFO
4. The loop engine creates the FIFO on startup if it doesn't exist
5. Valid commands: `mode manual|a|b|c`, `send <macro>`, `status`, `quit`
6. The loop runs in a screen session (`nxui_prog`) started by Flask app

## Notes for AI Assistants

- This is a working production system deployed on a Raspberry Pi
- Make minimal, surgical changes to avoid breaking existing functionality
- Preserve the existing code style and patterns
- Security is critical - always validate inputs and prevent injection attacks
- The deployment environment has specific constraints (paths, permissions, dependencies)
- When in doubt, follow the patterns already established in the codebase
