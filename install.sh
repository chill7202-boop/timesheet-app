#!/bin/bash

echo "=============================="
echo " Timesheet - Installer"
echo "=============================="
echo ""

if ! command -v python3 &>/dev/null; then
  echo "ERROR: Python not found. Please install Python from python.org"
  exit 1
fi

echo "Installing required packages..."
pip3 install streamlit duckdb pandas 2>/dev/null || python3 -m pip install streamlit duckdb pandas

echo ""
echo "=============================="
echo " Installation complete!"
echo " Run ./start.sh to launch the app."
echo "=============================="
