"""Parse bank / UPI / Google Pay messages into transaction details.

The user copies a message such as
    "Rs.250.00 debited from A/c XX1234 on 25-10-26 to VPA swiggy@icici (UPI Ref No 123456789012)"
and parse_message() extracts the amount, debit/credit, merchant, date,
payment method and a guessed category. Nothing is sent anywhere: all parsing
is done with regular expressions inside this file.
"""
import re
from datetime import date, datetime

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

DEBIT_RE = re.compile(r"\b(debited|spent|paid|sent|withdrawn|purchased?|dr)\b", re.I)
CREDIT_RE = re.compile(r"\b(credited|received|deposited|refund(?:ed)?|cr)\b", re.I)
AMOUNT_RE = re.compile(r"(?<![A-Za-z])(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?)", re.I)
AMOUNT_FALLBACK_RE = re.compile(r"\b(?:debited|credited)\s*(?:by|for|with)\s*([\d,]+(?:\.\d{1,2})?)", re.I)
REF_RE = re.compile(r"(?:ref(?:erence)?(?:\s*no)?\.?|utr|txn(?:\s*id)?|rrn)[\s:.#-]*(\d{6,})", re.I)

# merchant text: starts with letter/digit, lazy, stops before typical trailing words
STOP = r"(?=\s*(?:\(|\bon\b|ref|\bupi\b|\btxn\b|\bvia\b|\busing\b|\bthrough\b|\bfrom\b|\bavl\b|\bbal\b|\bif\b|\bnot\b|\bto\b|\bat\b|[.,;]\s|[.,;]?\s*$|\d{1,2}[-/]\w))"
NAME = r"([A-Za-z0-9][A-Za-z0-9 ._@&'\-]{1,40}?)"
EXPENSE_PATTERNS = [
    re.compile(r"(?:trf to|transfer to|paid to|\bto)\s+(?:vpa\s+)?" + NAME + STOP, re.I),
    re.compile(r"(?:towards|\bat)\s+" + NAME + STOP, re.I),
]
INCOME_PATTERNS = [
    re.compile(r"(?:\bfrom|\bby|sender)\s+(?:vpa\s+)?" + NAME + STOP, re.I),
]
BAD_START = ("your", "a/c", "ac ", "acct", "account", "bank", "xx", "upi", "neft", "imps", "rtgs",
             "cheque", "clearing", "card", "ref", "the ", "you")

CATEGORY_KEYWORDS = [
    ("Rent", [r"\brent\b", "landlord", "house rent"]),
    ("Utilities", ["electric", "mseb", "adani electricity", "tata power", "bses", r"\bgas\b", r"\bmgl\b", "water bill",
                   "broadband", "airtel", "jio", "vodafone", r"\bvi\b", "bsnl", "recharge", r"\bdth\b", "tata ?sky",
                   "postpaid", "prepaid", "bbps"]),
    ("Groceries", ["instamart", "blinkit", "zepto", "bigbasket", "grocer", "dmart", "supermarket", "jiomart",
                   "reliance fresh", "milk", "vegetable", "kirana", "provision"]),
    ("Subscriptions", ["netflix", "spotify", "prime video", "hotstar", "youtube", "google play", "icloud", "subscription"]),
    ("Entertainment", ["bookmyshow", "pvr", "inox", "cinema", "movie", "concert", r"\bgames?\b", "steam", "playstation"]),
    ("Education", ["school", "college", "tuition", "university", "udemy", "coursera", "byju", "unacademy",
                   r"\bexam", r"\bcourse", "stationery", r"\bbooks?\b", "library"]),
    ("Health", ["pharm", "apollo", "medplus", "1mg", "netmeds", "hospital", "clinic", "doctor", "medical",
                "diagnostic", r"\blab\b", "dental"]),
    ("Travel", ["makemytrip", "goibibo", "cleartrip", "ixigo", r"\boyo\b", "airline", "indigo", "air india", "vistara",
                "spicejet", "irctc", "redbus", "resort", "airbnb", "booking\\.com"]),
    ("Transport", ["uber", r"\bola\b", "rapido", "metro", "petrol", "diesel", "fuel", "hpcl", "bpcl", "iocl",
                   "indian oil", "fastag", "parking", r"\btoll\b", r"\bcab\b", r"\bauto\b", r"\bbus\b", "railway"]),
    ("Shopping", ["amazon", "flipkart", "myntra", "ajio", "meesho", "nykaa", "decathlon", "croma", "lenskart",
                  r"\bmall\b", "fashion", "clothing", r"\bshop\b", r"\bstore\b"]),
    ("Food & Dining", ["swiggy", "zomato", "restaurant", "cafe", "coffee", "pizza", "domino", "mcdonald", "kfc",
                       "burger", "starbucks", "bakery", "biryani", "dhaba", "canteen", r"\bfood", "dining", "eatery",
                       r"\bchai\b", "juice", "ice ?cream"]),
]
INCOME_KEYWORDS = [
    ("Salary", ["salary", "payroll"]),
    ("Freelance", ["freelance", "invoice", "client"]),
    ("Investments", ["interest", "dividend", "mutual fund", "stock", "sip"]),
    ("Gift", [r"\bgift\b"]),
]


def _parse_amount(text):
    for m in AMOUNT_RE.finditer(text):
        before = text[max(0, m.start() - 25):m.start()].lower()
        if any(w in before for w in ("bal", "avl", "available", "limit")):
            continue
        return float(m.group(1).replace(",", ""))
    m = AMOUNT_FALLBACK_RE.search(text)
    return float(m.group(1).replace(",", "")) if m else None


def _make_date(d, mth, y, today):
    try:
        y = int(y)
        y += 2000 if y < 100 else 0
        out = date(y, int(mth), int(d))
    except ValueError:
        return None
    return out if date(today.year - 5, 1, 1) <= out <= today else None


def _parse_date(text, today):
    for m in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text):
        d = _make_date(m.group(3), m.group(2), m.group(1), today)
        if d:
            return d
    for m in re.finditer(r"\b(\d{1,2})[-/. ]?([A-Za-z]{3})[A-Za-z]*[-/. ]?(\d{2,4})\b", text):
        mon = MONTHS.get(m.group(2).lower())
        if mon:
            d = _make_date(m.group(1), mon, m.group(3), today)
            if d:
                return d
    for m in re.finditer(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})\b", text):
        d = _make_date(m.group(1), m.group(2), m.group(3), today)
        if d:
            return d
    return None


def _clean_merchant(cand):
    cand = cand.strip(" .,-;:")
    if "@" in cand:
        cand = cand.split("@")[0]
    cand = cand.strip(" .,-;:")
    if cand.islower() or cand.isupper():
        cand = cand.title()
    return cand[:40]


def _find_merchant(text, patterns):
    for pat in patterns:
        for m in pat.finditer(text):
            cand = m.group(1).strip()
            low = cand.lower()
            if low.startswith(BAD_START) or re.fullmatch(r"[\d\-/.\s]+", cand):
                continue
            cleaned = _clean_merchant(cand)
            if len(cleaned) >= 2:
                return cleaned
    return None


def _guess_category(text_lower, tx_type, allowed):
    table = CATEGORY_KEYWORDS if tx_type == "Expense" else INCOME_KEYWORDS
    for category, words in table:
        if any(re.search(w if w.startswith(("\\b", "(")) else r"\b" + w, text_lower) for w in words):
            return category if (not allowed or category in allowed) else "Other"
    return "Other"


def _guess_method(low):
    if re.search(r"\b(upi|vpa|gpay|google ?pay|phonepe|paytm)\b|@\w+", low):
        return "UPI"
    if re.search(r"\b(?:paid|received|sent)\s+(?:you\s+)?₹", low):   # short Google Pay style notifications
        return "UPI"
    if "credit card" in low:
        return "Credit Card"
    if "debit card" in low or re.search(r"\bcard\b", low):
        return "Debit Card"
    if re.search(r"\b(neft|imps|rtgs|net ?banking)\b", low):
        return "Net Banking"
    if re.search(r"\batm\b", low):
        return "Cash"
    return "Other"


def parse_message(text, today=None, expense_categories=None, income_categories=None):
    """Return a dict. result['ok'] is False (with result['error']) when nothing usable is found."""
    today = today or date.today()
    raw = " ".join((text or "").split())
    if not raw:
        return {"ok": False, "error": "Please paste a bank, UPI or Google Pay message first."}
    low = raw.lower()

    if re.search(r"\b(requested|collect request|payment request)\b", low):
        return {"ok": False, "error": "This looks like a payment request, not a completed transaction."}
    if re.search(r"\b(failed|declined|unsuccessful|insufficient)\b", low):
        return {"ok": False, "error": "This message says the payment failed, so nothing was added."}

    amount = _parse_amount(raw)
    if not amount or amount <= 0:
        return {"ok": False, "error": "I could not find an amount (like Rs 250 or ₹250) in this message."}

    paid_you = re.search(r"\b(?:paid|sent)\s+you\b", low)
    d_hit, c_hit = DEBIT_RE.search(raw), CREDIT_RE.search(raw)
    if paid_you:
        tx_type = "Income"
    elif d_hit and (not c_hit or d_hit.start() < c_hit.start()):
        tx_type = "Expense"
    elif c_hit:
        tx_type = "Income"
    else:
        return {"ok": False, "error": "I could not tell whether this was money going out or coming in."}

    if paid_you:
        m = re.match(r"\s*([A-Za-z][A-Za-z .'-]{1,40}?)\s+(?:paid|sent)\s+you", raw, re.I)
        merchant = _clean_merchant(m.group(1)) if m else None
    else:
        merchant = _find_merchant(raw, EXPENSE_PATTERNS if tx_type == "Expense" else INCOME_PATTERNS)

    allowed = expense_categories if tx_type == "Expense" else income_categories
    category = _guess_category(low, tx_type, allowed)
    ref = REF_RE.search(raw)
    note = merchant or ("Money received" if tx_type == "Income" else "Added from message")
    if ref:
        note += f" (Ref {ref.group(1)})"

    return {"ok": True, "amount": amount, "type": tx_type, "merchant": merchant, "category": category,
            "payment_method": _guess_method(low), "date": _parse_date(raw, today), "note": note[:100]}
