# VSCode Project Setup

This project uses **mise** to automatically manage tool versions (Python, Node.js) and the Python virtual environment.

## First-time setup

### 1. Install mise via Homebrew

```bash
brew install mise
```

Mise is a unified version manager that reads `.python-version`, `.node-version`, and manages environments automatically.

### 2. Install tools and create virtualenv

From the project root:

```bash
mise install
```

This automatically:
- Installs Python 3.14.6 (from `.python-version`)
- Installs Node.js 26.5.0 (from `.node-version`)
- Creates `.venv` virtualenv (configured in `.mise.toml`)
- Adds `.venv/bin` to PATH

### 3. Install project dependencies

```bash
mise run setup
```

This installs:
- Python dependencies: `pip install -e ".[dev]"`
- Frontend dependencies: `npm install`

Or manually:
```bash
.venv/bin/python -m pip install -e ".[dev]"
cd frontend && npm install
```

### 4. Open in VSCode

VSCode will prompt to select the Python interpreter. Choose:

- **Suggested**: `.venv/bin/python` (already configured in `.vscode/settings.json`)

Mise automatically manages PATH so Python and Node.js tools work without additional configuration.

### 5. Verify setup

- Python interpreter shows `.venv/bin/python` in VSCode status bar
- `.venv/bin/python --version` outputs 3.14.6
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

### Automatic virtualenv management

Mise automatically:
- Creates `.venv` on first `mise install`
- Manages Python version inside `.venv` (linked from mise Python 3.14.6)
- Activates `.venv` when entering the directory
- Cleans up if `.mise.toml` configuration changes

To recreate `.venv` from scratch:

```bash
rm -rf .venv
mise install
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
- **`.mise.toml`** — Mise configuration (tasks, environment, additional tools)

This approach is **tool-agnostic**: if your team later switches from mise to nvm or pyenv, the version files still work (though automatic venv creation is mise-specific).

## Extensions

Recommended extensions (auto-prompted in VSCode):

- **jdx.mise** - Mise version manager integration
- **ms-python.python** - Python language support and debugging
- **ms-python.debugpy** - Python debugger
- **charliermarsh.ruff** - Ruff linter integration
- **dbaeumer.vscode-eslint** - ESLint integration
- **esbenp.prettier-vscode** - Prettier formatter
- **ryanluker.vscode-coverage-gutters** - Coverage report visualization

