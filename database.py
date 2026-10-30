"""Database layer for the Personal Expense Tracker.

Uses PostgreSQL (e.g. Neon) when a DATABASE_URL is provided in Streamlit
secrets or as an environment variable. Otherwise falls back to a local
SQLite file, so the app still runs on your own computer with no setup.
"""
import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager

import pandas as pd

DB_PATH = os.environ.get("EXPENSE_DB", "expense_tracker.db")


def _get_database_url():
    try:
        import streamlit as st
        return st.secrets["DATABASE_URL"]
    except Exception:
        return os.environ.get("DATABASE_URL")


DATABASE_URL = _get_database_url()
USE_PG = bool(DATABASE_URL)
_initialized = False


@contextmanager
def connect():
    if USE_PG:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _sql(query: str) -> str:
    return query.replace("?", "%s") if USE_PG else query


def _run(query, params=()):
    with connect() as conn:
        conn.cursor().execute(_sql(query), params)


def _fetch(query, params=()):
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(_sql(query), params)
        cols = [d[0] for d in cur.description]
        return cols, cur.fetchall()


def _integrity_errors():
    errors = [sqlite3.IntegrityError]
    if USE_PG:
        import psycopg2
        errors.append(psycopg2.IntegrityError)
    return tuple(errors)


def init_db():
    global _initialized
    if _initialized:
        return
    pk = "SERIAL PRIMARY KEY" if USE_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
    schema = f"""
        CREATE TABLE IF NOT EXISTS users (
            id {pk},
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id {pk},
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date TEXT NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('Income', 'Expense')),
            category TEXT NOT NULL,
            amount DOUBLE PRECISION NOT NULL CHECK (amount > 0),
            payment_method TEXT,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS budgets (
            id {pk},
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            monthly_limit DOUBLE PRECISION NOT NULL CHECK (monthly_limit > 0),
            UNIQUE (user_id, category)
        );
        CREATE INDEX IF NOT EXISTS idx_tx_user_date ON transactions(user_id, date);
    """
    with connect() as conn:
        if USE_PG:
            conn.cursor().execute(schema)
        else:
            conn.executescript(schema)
    _initialized = True


# ---------------------------------------------------------------- users
def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 100_000
    ).hex()


def create_user(username: str, password: str) -> bool:
    salt = secrets.token_hex(16)
    try:
        _run(
            "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
            (username.strip().lower(), _hash(password, salt), salt),
        )
        return True
    except _integrity_errors():
        return False


def verify_user(username: str, password: str):
    _, rows = _fetch(
        "SELECT id, username, password_hash, salt FROM users WHERE username = ?",
        (username.strip().lower(),),
    )
    if rows:
        uid, uname, pw_hash, salt = rows[0]
        if secrets.compare_digest(pw_hash, _hash(password, salt)):
            return {"id": int(uid), "username": uname}
    return None


# --------------------------------------------------------- transactions
def add_transaction(user_id, date, tx_type, category, amount, payment_method, note):
    _run(
        """INSERT INTO transactions
           (user_id, date, type, category, amount, payment_method, note)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (int(user_id), str(date), tx_type, category, float(amount), payment_method, note),
    )


def update_transaction(user_id, tx_id, date, tx_type, category, amount, payment_method, note):
    _run(
        """UPDATE transactions
           SET date=?, type=?, category=?, amount=?, payment_method=?, note=?
           WHERE id=? AND user_id=?""",
        (str(date), tx_type, category, float(amount), payment_method, note,
         int(tx_id), int(user_id)),
    )


def delete_transaction(user_id, tx_id):
    _run("DELETE FROM transactions WHERE id=? AND user_id=?", (int(tx_id), int(user_id)))


def get_transactions(user_id, start=None, end=None, tx_type=None,
                     categories=None, search=None) -> pd.DataFrame:
    query = (
        "SELECT id, date, type, category, amount, payment_method, note "
        "FROM transactions WHERE user_id = ?"
    )
    params = [int(user_id)]
    if start:
        query += " AND date >= ?"
        params.append(str(start))
    if end:
        query += " AND date <= ?"
        params.append(str(end))
    if tx_type and tx_type != "All":
        query += " AND type = ?"
        params.append(tx_type)
    if categories:
        query += f" AND category IN ({','.join('?' * len(categories))})"
        params.extend(categories)
    if search:
        query += " AND (LOWER(COALESCE(note, '')) LIKE LOWER(?) OR LOWER(category) LIKE LOWER(?))"
        params.extend([f"%{search}%", f"%{search}%"])
    query += " ORDER BY date DESC, id DESC"
    cols, rows = _fetch(query, params)
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)
    return df


# -------------------------------------------------------------- budgets
def set_budget(user_id, category, limit):
    _run(
        """INSERT INTO budgets (user_id, category, monthly_limit) VALUES (?, ?, ?)
           ON CONFLICT (user_id, category) DO UPDATE SET monthly_limit = excluded.monthly_limit""",
        (int(user_id), category, float(limit)),
    )


def get_budgets(user_id) -> pd.DataFrame:
    cols, rows = _fetch(
        "SELECT category, monthly_limit FROM budgets WHERE user_id = ? ORDER BY category",
        (int(user_id),),
    )
    df = pd.DataFrame(rows, columns=cols)
    df["monthly_limit"] = df["monthly_limit"].astype(float)
    return df


def delete_budget(user_id, category):
    _run("DELETE FROM budgets WHERE user_id=? AND category=?", (int(user_id), category))
