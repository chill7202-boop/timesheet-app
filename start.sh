#!/bin/bash

echo "=============================="
echo " Timesheet - Starting..."
echo "=============================="
echo ""

if ! command -v python3 &>/dev/null; then
  echo "ERROR: Python not found. Please run ./install.sh first."
  exit 1
fi

if ! python3 -c "import streamlit" &>/dev/null; then
  echo "ERROR: Streamlit not found. Please run ./install.sh first."
  exit 1
fi

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting at http://localhost:8501"
echo "Press CTRL+C to stop."
echo ""

(sleep 3 && open http://localhost:8501) &

streamlit run "$DIR/timesheet_app.py" --server.headless true
