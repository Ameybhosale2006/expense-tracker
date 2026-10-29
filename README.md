# 💰 Personal Expense Tracker

A mini project built with **Python, Streamlit, SQLite and Pandas**.

## Features
- User registration & login (passwords hashed with PBKDF2 + salt)
- Daily income / expense entry (date, amount, category, payment method, note)
- Edit and delete transactions
- Filters: date range, type, multiple categories, text search, sorting
- Monthly dashboard: income, expenses, balance, savings rate, change vs last month
- Charts: spending by category (donut), daily income vs expense, 6-month trend
- Top categories and biggest expenses of the month
- Monthly category budgets with progress bars and over-budget alerts
- CSV export and import (backup / restore)

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud
1. Push this folder to a GitHub repository.
2. Go to https://share.streamlit.io, click **New app**, pick the repo, branch `main`, main file `app.py`.
3. Click **Deploy**.

> Note: Streamlit Cloud storage is temporary - the SQLite file can reset when the app restarts.
> Use **Import / Export** to back up your data regularly.

## Project structure
| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI (pages, forms, charts) |
| `database.py` | SQLite database functions |
| `requirements.txt` | Python dependencies |
