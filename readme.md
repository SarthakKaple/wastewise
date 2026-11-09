# WasteWise – Home Resource Waste Detector

A software-only Python web app that helps households find where they waste
water, electricity and gas. It gives a Waste Score (0–100), flags unusually
high days with the IQR rule, shows a weekly trend, checks for overnight water
leaks and suggests savings.

## Tech
Python, Flask, SQLite, pandas, NumPy, Chart.js, pytest

## Run it
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000

## Test it
    pytest -v

## Status
Core features complete (45 automated tests). Planned: real-data testing,
stronger detection of long high-usage periods, a desktop version.

Team project, Vishwakarma Institute of Technology, Pune.