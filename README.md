# 💰 Personal Expense Tracker

A mini project built with **Python, Streamlit, SQLite and Pandas**.

## Features
- User registration & login (passwords hashed with PBKDF2 + salt)
- Daily income / expense entry (date, amount, category, payment method, note)
- **Quick Add:** paste a bank / UPI / Google Pay message and the form is filled in automatically (amount, debit or credit, merchant, date, category, payment method)
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

> Set a `DATABASE_URL` secret (Neon PostgreSQL) in Streamlit Cloud, because its file storage is temporary and a SQLite file can reset when the app restarts.

## Project structure
| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI (pages, forms, charts) |
| `database.py` | Database functions (Neon PostgreSQL, SQLite fallback) |
| `sms_parser.py` | Reads pasted bank / UPI messages for Quick Add |
| `requirements.txt` | Python dependencies |
