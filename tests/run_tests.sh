#!/usr/bin/env bash
# Run all tests using uv
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== Running Digital Workforce Platform Tests ==="
PYTHONPATH="$(pwd)" uv run --python 3.13 --with pyyaml --with pydantic --with pytest --with anthropic --with "langgraph>=0.2" -- python -m pytest tests/ -v --tb=short
echo "=== All tests complete ==="
