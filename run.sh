#!/bin/bash
# Slay the Spire AI Agent — Run Script
#
# Usage:
#   ./run.sh                    # Run with DEEPSEEK_API_KEY env var
#   ./run.sh --api-key KEY      # Run with specific API key
#   ./run.sh --help             # Show all options

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Change to engine directory (required for imports to work)
cd "$SCRIPT_DIR/engine"

# Load API key from config if it exists
if [ -f "$SCRIPT_DIR/config/api_key.yaml" ]; then
    # Try to extract API key from yaml (basic parsing)
    API_KEY=$(grep 'api_key' "$SCRIPT_DIR/config/api_key.yaml" 2>/dev/null | head -1 | sed 's/.*: *"\(.*\)"/\1/')
    if [ -n "$API_KEY" ] && [ "$API_KEY" != "sk-your-deepseek-api-key-here" ]; then
        export DEEPSEEK_API_KEY="$API_KEY"
    fi
fi

# Check if API key is available
if [ -z "$DEEPSEEK_API_KEY" ]; then
    # Check if --api-key was passed
    for arg in "$@"; do
        if [ "$arg" = "--help" ]; then
            python3 main.py --help
            exit 0
        fi
    done
fi

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Run the AI agent
exec python3 main.py "$@"
