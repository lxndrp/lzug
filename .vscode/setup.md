# VSCode Project Setup

This project uses **pyenv** to manage Python versions locally.

## First-time setup

### 1. Install pyenv (macOS / Linux)

```bash
brew install pyenv
```

See https://github.com/pyenv/pyenv#installation for other platforms.

### 2. Install Python 3.11.9

Run from the project root:

```bash
pyenv install
```

This reads `.python-version` and installs the pinned version.

### 3. Create virtual environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

### 4. Open in VSCode

VSCode will prompt to select the Python interpreter. Choose the venv:

- **Suggested**: `.venv/bin/python` from the workspace

This is already configured in `.vscode/settings.json` as the default.

### 5. Verify

VSCode should show:

- Python interpreter: `.venv/bin/python` in the bottom status bar
- Linting: ruff and black active (no errors in Output > Python)
- ESLint: active in frontend files (no errors in Output > ESLint)

## Why pyenv?

- Ensures all team members use Python 3.11.9
- Prevents "works on my machine" version mismatches
- Matches CI version exactly
- Works alongside venv for dependency isolation

## Extensions

Recommended extensions (auto-prompted in VSCode):

- **ms-python.python** - Python language support and debugging
- **ms-python.debugpy** - Python debugger
- **charliermarsh.ruff** - Ruff linter integration
- **dbaeumer.vscode-eslint** - ESLint integration
- **esbenp.prettier-vscode** - Prettier formatter
- **ryanluker.vscode-coverage-gutters** - Coverage report visualization
