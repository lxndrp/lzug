# VSCode Project Setup

This project uses **mise** to manage tool versions (Python, Node.js) via standard version files.

## First-time setup

### 1. Install mise via Homebrew

```bash
brew install mise
```

Mise is a unified version manager that reads `.python-version`, `.node-version`, and more.

### 2. Install pinned versions

From the project root, mise automatically reads `.python-version` and `.node-version`:

```bash
mise install
```

This installs:
- Python 3.14.6 (from `.python-version`)
- Node.js 26.5.0 (from `.node-version`)

### 3. Create virtual environment (Python only)

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Then install frontend dependencies:

```bash
cd frontend && npm install
```

Or use the mise task:

```bash
mise run setup
```

### 4. Open in VSCode

VSCode will prompt to select the Python interpreter. Choose:

- **Suggested**: `.venv/bin/python` (already configured in `.vscode/settings.json`)

Mise automatically sets PATH so Python and Node.js tools work without additional configuration.

### 5. Verify setup

- Python interpreter shows `.venv/bin/python` in VSCode status bar
- `python --version` outputs 3.14.6
- `node --version` outputs v26.5.0
- Linting active (ruff, black, ESLint)

## Using mise

### Run tests

```bash
mise run test
```

### Start development servers (parallel)

```bash
mise run dev
```

### Sync Homebrew-installed versions (optional)

If you install Python or Node.js via Homebrew, make them available to mise:

```bash
mise sync python
mise sync nodejs
```

This symlinks Homebrew versions into mise, allowing you to switch between them.

### Adding tools to version files

To add Go support, create `.go-version`:

```bash
echo "1.21" > .go-version
mise install
```

Mise reads all version files automatically.

## Version files

- **`.python-version`** — Python version (compatible with pyenv)
- **`.node-version`** — Node.js version (compatible with nvm)
- **`.mise.toml`** — Mise configuration (tasks, additional tools)

This approach is **tool-agnostic**: if your team later switches from mise to nvm or pyenv, the version files still work.

## Extensions

Recommended extensions (auto-prompted in VSCode):

- **jdx.mise** - Mise version manager integration
- **ms-python.python** - Python language support and debugging
- **ms-python.debugpy** - Python debugger
- **charliermarsh.ruff** - Ruff linter integration
- **dbaeumer.vscode-eslint** - ESLint integration
- **esbenp.prettier-vscode** - Prettier formatter
- **ryanluker.vscode-coverage-gutters** - Coverage report visualization


