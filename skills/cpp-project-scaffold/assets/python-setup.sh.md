# python/setup.sh Template

```bash
#!/usr/bin/env bash
# Setup unified Python environment for project tooling
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"

if [ -d "$VENV_DIR" ]; then
    echo "Python venv already exists at $VENV_DIR"
    echo "To recreate, delete it first: rm -rf $VENV_DIR"
else
    echo "Creating Python venv at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "${SCRIPT_DIR}/requirements.txt"

echo ""
echo "Python environment ready at $VENV_DIR"
echo "Activate with: source $VENV_DIR/bin/activate"
```
