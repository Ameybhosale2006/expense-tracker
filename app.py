"""Personal Expense Tracker - Streamlit app.  Run with:  streamlit run app.py"""
import calendar
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

import database as db

st.set_page_config(page_title="Personal Expense Tracker", page_icon="💰", layout="wide")
db.init_db()

CURRENCY = "₹"
EXPENSE_CATEGORIES = [
    "Food & Dining", "Groceries", "Rent", "Transport", "Utilities", "Shopping",
    "Entertainment", "Health", "Education", "Travel", "Subscriptions", "Other",
]
INCOME_CATEGORIES = ["Salary", "Freelance", "Business", "Investments", "Gift", "Other"]
ALL_CATEGORIES = sorted(set(EXPENSE_CATEGORIES + INCOME_CATEGORIES))
PAYMENT_METHODS = ["Cash", "UPI", "Debit Card", "Credit Card", "Net Banking", "Other"]
TYPE_COLORS = alt.Scale(domain=["Income", "Expense"], range=["#2e9e6b", "#e0524d"])


def money(x: float) -> str:
    return f"{CURRENCY}{x:,.2f}"


# ------------------------------------------------------------------ auth
def auth_screen():
    st.title("💰 Personal Expense Tracker")
    st.caption("Track your daily income and expenses, set budgets and see monthly insights.")
    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", type="primary"):
                user = db.verify_user(username, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

    with tab_register:
        with st.form("register_form"):
            new_user = st.text_input("Choose a username")
            new_pass = st.text_input("Choose a password (min 6 characters)", type="password")
            confirm = st.text_input("Confirm password", type="password")
            if st.form_submit_button("Create account"):
                if len(new_user.strip()) < 3:
                    st.error("Username must be at least 3 characters.")
                elif len(new_pass) < 6:
                    st.error("Password must be at least 6 characters.")
                elif new_pass != confirm:
                    st.error("Passwords do not match.")
                elif db.create_user(new_user, new_pass):
                    st.success("Account created! Please log in from the Login tab.")
                else:
                    st.error("That username is already taken.")


# ------------------------------------------------------------- dashboard
def dashboard(user_id):
    st.header("📊 Monthly Dashboard")
    df = db.get_transactions(user_id)
    today = date.today()

    c1, c2 = st.columns(2)
    years = sorted({today.year, *df["date"].dt.year.tolist()}, reverse=True)
    year = c1.selectbox("Year", years)
    month = c2.selectbox(
        "Month", list(range(1, 13)), index=today.month - 1,
        format_func=lambda m: calendar.month_name[m],
    )

    in_month = df[(df["date"].dt.year == year) & (df["date"].dt.month == month)]
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    prev = df[(df["date"].dt.year == prev_year) & (df["date"].dt.month == prev_month)]

    income = in_month.loc[in_month["type"] == "Income", "amount"].sum()
    expense = in_month.loc[in_month["type"] == "Expense", "amount"].sum()
    prev_income = prev.loc[prev["type"] == "Income", "amount"].sum()
    prev_expense = prev.loc[prev["type"] == "Expense", "amount"].sum()
    balance = income - expense
    savings_rate = (balance / income * 100) if income > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Income", money(income), money(income - prev_income) + " vs last month")
    m2.metric("Expenses", money(expense), money(expense - prev_expense) + " vs last month",
              delta_color="inverse")
    m3.metric("Balance", money(balance))
    m4.metric("Savings rate", f"{savings_rate:.1f}%")

    if in_month.empty:
        st.info("No transactions for this month yet. Add some from the sidebar menu.")
        return

    # Budget alerts
    budgets = db.get_budgets(user_id)
    spent_by_cat = in_month[in_month["type"] == "Expense"].groupby("category")["amount"].sum()
    for _, b in budgets.iterrows():
        spent = spent_by_cat.get(b["category"], 0.0)
        if spent > b["monthly_limit"]:
            st.error(f"🚨 Over budget on **{b['category']}**: {money(spent)} of {money(b['monthly_limit'])}")
        elif spent >= 0.8 * b["monthly_limit"]:
            st.warning(f"⚠️ **{b['category']}** is at {spent / b['monthly_limit'] * 100:.0f}% of its budget")

    left, right = st.columns(2)

    with left:
        st.subheader("Spending by category")
        exp_cat = (in_month[in_month["type"] == "Expense"]
                   .groupby("category", as_index=False)["amount"].sum())
        if exp_cat.empty:
            st.caption("No expenses this month.")
        else:
            donut = alt.Chart(exp_cat).mark_arc(innerRadius=60).encode(
                theta="amount:Q",
                color=alt.Color("category:N", legend=alt.Legend(title="Category")),
                tooltip=["category", alt.Tooltip("amount:Q", format=",.2f")],
            )
            st.altair_chart(donut, use_container_width=True)

    with right:
        st.subheader("Daily income vs expense")
        daily = in_month.groupby([in_month["date"].dt.day.rename("day"), "type"],
                                 as_index=False)["amount"].sum()
        bars = alt.Chart(daily).mark_bar().encode(
            x=alt.X("day:O", title="Day of month"),
            y=alt.Y("amount:Q", title=f"Amount ({CURRENCY})"),
            color=alt.Color("type:N", scale=TYPE_COLORS, legend=alt.Legend(title="")),
            xOffset="type:N",
            tooltip=["day", "type", alt.Tooltip("amount:Q", format=",.2f")],
        )
        st.altair_chart(bars, use_container_width=True)

    st.subheader("Last 6 months trend")
    periods = pd.period_range(end=pd.Period(f"{year}-{month:02d}"), periods=6, freq="M")
    tmp = df.assign(month=df["date"].dt.to_period("M"))
    trend = (tmp.groupby(["month", "type"])["amount"].sum().unstack(fill_value=0)
             .reindex(periods, fill_value=0))
    for col in ("Income", "Expense"):
        if col not in trend:
            trend[col] = 0.0
    trend = trend[["Income", "Expense"]]
    trend.index = [p.strftime("%b %Y") for p in periods]
    long = trend.reset_index(names="month").melt("month", var_name="type", value_name="amount")
    line = alt.Chart(long).mark_bar().encode(
        x=alt.X("month:N", sort=list(trend.index), title=""),
        y=alt.Y("amount:Q", title=f"Amount ({CURRENCY})"),
        color=alt.Color("type:N", scale=TYPE_COLORS, legend=alt.Legend(title="")),
        xOffset="type:N",
        tooltip=["month", "type", alt.Tooltip("amount:Q", format=",.2f")],
    )
    st.altair_chart(line, use_container_width=True)

    t1, t2 = st.columns(2)
    with t1:
        st.subheader("Top spending categories")
        if not exp_cat.empty:
            top = exp_cat.sort_values("amount", ascending=False).head(5).copy()
            top["share"] = (top["amount"] / expense * 100).round(1).astype(str) + "%"
            top["amount"] = top["amount"].map(money)
            st.dataframe(top.rename(columns={"category": "Category", "amount": "Spent", "share": "Share"}),
                         hide_index=True, use_container_width=True)
    with t2:
        st.subheader("Biggest expenses")
        big = in_month[in_month["type"] == "Expense"].nlargest(5, "amount")
        if not big.empty:
            st.dataframe(
                pd.DataFrame({
                    "Date": big["date"].dt.strftime("%d %b"),
                    "Category": big["category"],
                    "Amount": big["amount"].map(money),
                    "Note": big["note"],
                }), hide_index=True, use_container_width=True)


# --------------------------------------------------------- add transaction
def add_page(user_id):
    st.header("➕ Add Transaction")
    tx_type = st.radio("Type", ["Expense", "Income"], horizontal=True)
    categories = EXPENSE_CATEGORIES if tx_type == "Expense" else INCOME_CATEGORIES
    with st.form("add_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        tx_date = c1.date_input("Date", value=date.today(), max_value=date.today())
        amount = c2.number_input(f"Amount ({CURRENCY})", min_value=0.0, step=10.0, format="%.2f")
        category = c1.selectbox("Category", categories)
        method = c2.selectbox("Payment method", PAYMENT_METHODS)
        note = st.text_input("Note (optional)")
        if st.form_submit_button("Save transaction", type="primary"):
            if amount <= 0:
                st.error("Amount must be greater than zero.")
            else:
                db.add_transaction(user_id, tx_date, tx_type, category, amount, method, note.strip())
                st.success(f"{tx_type} of {money(amount)} saved under {category}.")


# ------------------------------------------------------------ transactions
def transactions_page(user_id):
    st.header("📋 Transactions")
    all_df = db.get_transactions(user_id)
    if all_df.empty:
        st.info("No transactions yet. Add your first one from the sidebar.")
        return

    with st.expander("🔍 Filters", expanded=True):
        f1, f2, f3 = st.columns(3)
        min_d, max_d = all_df["date"].min().date(), max(all_df["date"].max().date(), date.today())
        rng = f1.date_input("Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d)
        tx_type = f2.selectbox("Type", ["All", "Income", "Expense"])
        cats = f3.multiselect("Categories", ALL_CATEGORIES)
        s1, s2 = st.columns(2)
        search = s1.text_input("Search notes / category")
        sort_by = s2.selectbox("Sort by", ["Newest first", "Oldest first", "Highest amount", "Lowest amount"])

    start, end = (rng[0], rng[1]) if isinstance(rng, tuple) and len(rng) == 2 else (min_d, max_d)
    df = db.get_transactions(user_id, start, end, tx_type, cats, search.strip() or None)
    sort_map = {
        "Newest first": ("date", False), "Oldest first": ("date", True),
        "Highest amount": ("amount", False), "Lowest amount": ("amount", True),
    }
    col, asc = sort_map[sort_by]
    df = df.sort_values(col, ascending=asc)

    inc = df.loc[df["type"] == "Income", "amount"].sum()
    exp = df.loc[df["type"] == "Expense", "amount"].sum()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Records", len(df))
    m2.metric("Income", money(inc))
    m3.metric("Expenses", money(exp))
    m4.metric("Net", money(inc - exp))

    show = df.copy()
    show["date"] = show["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(
        show.rename(columns={"id": "ID", "date": "Date", "type": "Type", "category": "Category",
                             "amount": "Amount", "payment_method": "Payment", "note": "Note"}),
        hide_index=True, use_container_width=True,
        column_config={"Amount": st.column_config.NumberColumn(format=f"{CURRENCY}%.2f")},
    )
    st.download_button("⬇️ Download filtered data (CSV)",
                       show.drop(columns="id").to_csv(index=False), "transactions_filtered.csv", "text/csv")

    # Edit / delete
    st.subheader("✏️ Edit or delete a transaction")
    if df.empty:
        return
    options = {
        int(r.id): f"#{r.id} | {r.date:%d %b %Y} | {r.type} | {r.category} | {money(r.amount)}"
        for r in df.itertuples()
    }
    chosen = st.selectbox("Select a transaction", list(options), format_func=options.get)
    row = df[df["id"] == chosen].iloc[0]
    with st.form(f"edit_form_{chosen}"):
        c1, c2 = st.columns(2)
        e_date = c1.date_input("Date", value=row["date"].date(), max_value=date.today())
        e_amount = c2.number_input("Amount", min_value=0.01, value=float(row["amount"]), step=10.0)
        e_type = c1.selectbox("Type", ["Expense", "Income"], index=0 if row["type"] == "Expense" else 1)
        cat_options = sorted(set(ALL_CATEGORIES + [row["category"]]))
        e_cat = c2.selectbox("Category", cat_options, index=cat_options.index(row["category"]))
        pm_options = sorted(set(PAYMENT_METHODS + [row["payment_method"] or "Other"]))
        e_method = c1.selectbox("Payment method", pm_options, index=pm_options.index(row["payment_method"] or "Other"))
        e_note = c2.text_input("Note", value=row["note"] or "")
        b1, b2, _ = st.columns([1, 1, 4])
        save = b1.form_submit_button("Update", type="primary")
        remove = b2.form_submit_button("Delete")
    if save:
        db.update_transaction(user_id, chosen, e_date, e_type, e_cat, e_amount, e_method, e_note.strip())
        st.success("Transaction updated.")
        st.rerun()
    if remove:
        db.delete_transaction(user_id, chosen)
        st.success("Transaction deleted.")
        st.rerun()


# ----------------------------------------------------------------- budgets
def budgets_page(user_id):
    st.header("🎯 Monthly Budgets")
    with st.form("budget_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        cat = c1.selectbox("Category", EXPENSE_CATEGORIES)
        limit = c2.number_input(f"Monthly limit ({CURRENCY})", min_value=0.0, step=500.0)
        if st.form_submit_button("Set budget", type="primary"):
            if limit > 0:
                db.set_budget(user_id, cat, limit)
                st.success(f"Budget for {cat} set to {money(limit)}.")
            else:
                st.error("Limit must be greater than zero.")

    budgets = db.get_budgets(user_id)
    if budgets.empty:
        st.info("No budgets set yet.")
        return

    today = date.today()
    df = db.get_transactions(user_id)
    this_month = df[(df["date"].dt.year == today.year) & (df["date"].dt.month == today.month)
                    & (df["type"] == "Expense")]
    spent = this_month.groupby("category")["amount"].sum()

    st.subheader(f"Progress for {calendar.month_name[today.month]} {today.year}")
    for _, b in budgets.iterrows():
        s = float(spent.get(b["category"], 0.0))
        pct = s / b["monthly_limit"]
        c1, c2 = st.columns([5, 1])
        c1.write(f"**{b['category']}** — {money(s)} of {money(b['monthly_limit'])} ({pct * 100:.0f}%)")
        c1.progress(min(pct, 1.0))
        if c2.button("Remove", key=f"rm_{b['category']}"):
            db.delete_budget(user_id, b["category"])
            st.rerun()
        if pct > 1:
            c1.error(f"Over budget by {money(s - b['monthly_limit'])}")


# ------------------------------------------------------------ import/export
def data_page(user_id):
    st.header("💾 Import / Export Data")
    df = db.get_transactions(user_id)

    st.subheader("Export")
    if df.empty:
        st.caption("Nothing to export yet.")
    else:
        out = df.assign(date=df["date"].dt.strftime("%Y-%m-%d")).drop(columns="id")
        st.download_button("⬇️ Download all transactions (CSV)", out.to_csv(index=False),
                           "expense_tracker_backup.csv", "text/csv")

    st.subheader("Import")
    st.caption("CSV columns: date (YYYY-MM-DD), type (Income/Expense), category, amount, "
               "payment_method (optional), note (optional).")
    up = st.file_uploader("Upload CSV", type="csv")
    if up is not None and st.button("Import now", type="primary"):
        try:
            data = pd.read_csv(up)
            data.columns = [c.strip().lower() for c in data.columns]
            missing = {"date", "type", "category", "amount"} - set(data.columns)
            if missing:
                st.error(f"Missing columns: {', '.join(sorted(missing))}")
                return
            data["date"] = pd.to_datetime(data["date"]).dt.date
            data["type"] = data["type"].astype(str).str.strip().str.capitalize()
            data["amount"] = pd.to_numeric(data["amount"])
            if not data["type"].isin(["Income", "Expense"]).all() or (data["amount"] <= 0).any():
                st.error("Types must be Income/Expense and amounts must be positive.")
                return
            for r in data.fillna("").itertuples():
                db.add_transaction(user_id, r.date, r.type, str(r.category),
                                   r.amount, getattr(r, "payment_method", "") or "Other",
                                   str(getattr(r, "note", "")))
            st.success(f"Imported {len(data)} transactions.")
        except Exception as exc:
            st.error(f"Could not import file: {exc}")


# ------------------------------------------------------------------- main
def main():
    if "user" not in st.session_state:
        auth_screen()
        return

    user = st.session_state.user
    with st.sidebar:
        st.title("💰 Expense Tracker")
        st.write(f"Logged in as **{user['username']}**")
        page = st.radio("Menu", ["Dashboard", "Add Transaction", "Transactions", "Budgets", "Import / Export"])
        if st.button("Logout"):
            del st.session_state["user"]
            st.rerun()

    {
        "Dashboard": dashboard,
        "Add Transaction": add_page,
        "Transactions": transactions_page,
        "Budgets": budgets_page,
        "Import / Export": data_page,
    }[page](user["id"])


main()
