# VSCode Project Setup

This project uses **mise** to manage tool versions (Python, Node.js) across your team.

## First-time setup

### 1. Install mise via Homebrew

```bash
brew install mise
```

Mise is a unified version manager for Python, Node.js, Go, Ruby, and more.

### 2. Install pinned versions

From the project root:

```bash
mise install
```

This reads `.mise.toml` and installs:
- Python 3.14.6
- Node.js 26.5.0

Versions can be added to `.mise.toml` at any time (e.g., Go for future use).

### 3. Create virtual environment (Python only)

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

Then install frontend dependencies:

```bash
cd frontend && npm install
```

Or use mise tasks:

```bash
mise run setup
```

### 4. Open in VSCode

VSCode will prompt to select the Python interpreter. Choose:

- **Suggested**: `.venv/bin/python` (already configured in `.vscode/settings.json`)

Mise automatically sets PATH so Node.js tools work without additional configuration.

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

## Extensions

Recommended extensions (auto-prompted in VSCode):

- **jdx.mise** - Mise version manager integration
- **ms-python.python** - Python language support and debugging
- **ms-python.debugpy** - Python debugger
- **charliermarsh.ruff** - Ruff linter integration
- **dbaeumer.vscode-eslint** - ESLint integration
- **esbenp.prettier-vscode** - Prettier formatter
- **ryanluker.vscode-coverage-gutters** - Coverage report visualization

## Adding more tools to mise

Mise supports Go, Ruby, Rust, Deno, Java, and many more. To add Go support:

```toml
# .mise.toml
go = "1.21"
```

Then:

```bash
mise install
```

That's it—no plugins or complex configuration needed.

