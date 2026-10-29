"""Database layer for the Personal Expense Tracker (SQLite)."""
import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager

import pandas as pd

DB_PATH = os.environ.get("EXPENSE_DB", "expense_tracker.db")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('Income', 'Expense')),
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK (amount > 0),
                payment_method TEXT,
                note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                monthly_limit REAL NOT NULL CHECK (monthly_limit > 0),
                UNIQUE (user_id, category),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_tx_user_date ON transactions(user_id, date);
            """
        )


# ---------------------------------------------------------------- users
def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 100_000
    ).hex()


def create_user(username: str, password: str) -> bool:
    salt = secrets.token_hex(16)
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                (username.strip().lower(), _hash(password, salt), salt),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def verify_user(username: str, password: str):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip().lower(),)
        ).fetchone()
    if row and secrets.compare_digest(row["password_hash"], _hash(password, row["salt"])):
        return {"id": row["id"], "username": row["username"]}
    return None


# --------------------------------------------------------- transactions
def add_transaction(user_id, date, tx_type, category, amount, payment_method, note):
    with connect() as conn:
        conn.execute(
            """INSERT INTO transactions
               (user_id, date, type, category, amount, payment_method, note)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, str(date), tx_type, category, float(amount), payment_method, note),
        )


def update_transaction(user_id, tx_id, date, tx_type, category, amount, payment_method, note):
    with connect() as conn:
        conn.execute(
            """UPDATE transactions
               SET date=?, type=?, category=?, amount=?, payment_method=?, note=?
               WHERE id=? AND user_id=?""",
            (str(date), tx_type, category, float(amount), payment_method, note, tx_id, user_id),
        )


def delete_transaction(user_id, tx_id):
    with connect() as conn:
        conn.execute(
            "DELETE FROM transactions WHERE id=? AND user_id=?", (tx_id, user_id)
        )


def get_transactions(user_id, start=None, end=None, tx_type=None,
                     categories=None, search=None) -> pd.DataFrame:
    query = (
        "SELECT id, date, type, category, amount, payment_method, note "
        "FROM transactions WHERE user_id = ?"
    )
    params = [user_id]
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
        query += " AND (note LIKE ? OR category LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    query += " ORDER BY date DESC, id DESC"
    with connect() as conn:
        df = pd.read_sql_query(query, conn, params=params)
    df["date"] = pd.to_datetime(df["date"])
    return df


# -------------------------------------------------------------- budgets
def set_budget(user_id, category, limit):
    with connect() as conn:
        conn.execute(
            """INSERT INTO budgets (user_id, category, monthly_limit) VALUES (?, ?, ?)
               ON CONFLICT(user_id, category) DO UPDATE SET monthly_limit = excluded.monthly_limit""",
            (user_id, category, float(limit)),
        )


def get_budgets(user_id) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query(
            "SELECT category, monthly_limit FROM budgets WHERE user_id = ? ORDER BY category",
            conn, params=[user_id],
        )


def delete_budget(user_id, category):
    with connect() as conn:
        conn.execute(
            "DELETE FROM budgets WHERE user_id=? AND category=?", (user_id, category)
        )
