"""Online payments with Razorpay Payment Links (UPI, cards, netbanking, wallets).

How it works: GTD creates a payment link for the amount due on a booking, the customer pays on Razorpay's own
page, and GTD then asks Razorpay (server to server, with the secret key) whether that link was paid. Nothing the
browser says is trusted. Confirmed payments are written to the normal `payments` table, so the dashboards,
reports and "Paid / Unpaid" labels keep working.

Settings (Streamlit secrets or environment variables):
  GTD_RAZORPAY_KEY_ID      e.g. rzp_test_xxxxxxxx (test) or rzp_live_xxxxxxxx (live)
  GTD_RAZORPAY_KEY_SECRET  the matching secret
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

import db

API = "https://api.razorpay.com/v1"
LINK_LIFETIME_HOURS = 24
_TABLE_READY = False
_last_sync = {}


def _setting(name):
    """Reads a setting from the environment or from Streamlit secrets (also if it was pasted under a [section])."""
    val = os.environ.get(name)
    if val:
        return val.strip()
    try:
        import streamlit as st
        sec = st.secrets
        if name in sec:
            return str(sec[name]).strip()
        for k in sec:
            sub = sec[k]
            if hasattr(sub, "get") and sub.get(name):
                return str(sub[name]).strip()
    except Exception:
        pass
    return ""


def is_configured():
    return bool(_setting("GTD_RAZORPAY_KEY_ID") and _setting("GTD_RAZORPAY_KEY_SECRET"))


def is_test_mode():
    return _setting("GTD_RAZORPAY_KEY_ID").startswith("rzp_test_")


def _ensure_table():
    global _TABLE_READY
    if _TABLE_READY:
        return
    db.run("""CREATE TABLE IF NOT EXISTS online_payments(
      id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
      link_id TEXT UNIQUE NOT NULL, short_url TEXT NOT NULL, amount REAL NOT NULL,
      status TEXT NOT NULL DEFAULT 'created', payment_id TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL, paid_at TEXT)""")
    _TABLE_READY = True


def _call(method, path, payload=None):
    """Calls the Razorpay API. Raises RuntimeError with a readable message on failure."""
    key, secret = _setting("GTD_RAZORPAY_KEY_ID"), _setting("GTD_RAZORPAY_KEY_SECRET")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode())
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read().decode()).get("error", {}).get("description", "")
        except Exception:
            msg = ""
        raise RuntimeError(msg or f"Razorpay returned HTTP {exc.code}")
    except Exception as exc:
        raise RuntimeError(f"Could not reach Razorpay: {exc}")


# ---------------------------------------------------------------- confirming payments
def sync_link(row):
    """Asks Razorpay about one stored link and records the payment if it was paid. Returns True if newly paid."""
    info = _call("GET", f"/payment_links/{row['link_id']}")
    status = info.get("status", "created")
    if status == "paid":
        if db.q1("SELECT id FROM online_payments WHERE id=? AND status='paid'", (row["id"],)):
            return False
        pay_id = ""
        for p in info.get("payments") or []:
            if p.get("status") in ("captured", "authorized"):
                pay_id = p.get("payment_id", "")
                break
        amount = (info.get("amount_paid") or int(round(row["amount"] * 100))) / 100
        now = db.now_str()
        stmts = [("UPDATE online_payments SET status='paid', payment_id=?, paid_at=? WHERE id=?", (pay_id, now, row["id"])),
                 ("DELETE FROM payments WHERE booking_id=? AND status='pending'", (row["booking_id"],))]
        if not (pay_id and db.q1("SELECT id FROM payments WHERE reference=?", (pay_id,))):
            stmts.append(("INSERT INTO payments(booking_id,amount,method,status,reference,paid_at) VALUES(?,?,?,?,?,?)",
                          (row["booking_id"], amount, "online", "paid", pay_id or row["link_id"], now)))
        db.run_many(stmts)
        return True
    if status in ("expired", "cancelled"):
        db.run("UPDATE online_payments SET status=? WHERE id=?", (status, row["id"]))
    return False


def sync_booking(booking_id):
    _ensure_table()
    newly = 0
    for row in db.q("SELECT * FROM online_payments WHERE booking_id=? AND status='created'", (booking_id,)):
        try:
            newly += 1 if sync_link(row) else 0
        except RuntimeError as exc:
            print(f"[pay] could not check link {row['link_id']}: {exc}")
    return newly


def sync_customer(user_id, force=False):
    """Checks every open link of one customer's bookings (at most once every 8 seconds unless forced).
    Returns how many payments were newly confirmed."""
    if not is_configured():
        return 0
    now = time.time()
    if not force and now - _last_sync.get(user_id, 0) < 8:
        return 0
    _last_sync[user_id] = now
    _ensure_table()
    newly = 0
    rows = db.q("SELECT o.* FROM online_payments o JOIN bookings b ON b.id=o.booking_id "
                "WHERE b.customer_id=? AND o.status='created'", (user_id,))
    for row in rows:
        try:
            newly += 1 if sync_link(row) else 0
        except RuntimeError as exc:
            print(f"[pay] could not check link {row['link_id']}: {exc}")
    return newly


def sync_all():
    """Admin: checks every open link. Returns how many payments were newly confirmed."""
    if not is_configured():
        return 0
    _ensure_table()
    newly = 0
    for row in db.q("SELECT * FROM online_payments WHERE status='created'"):
        try:
            newly += 1 if sync_link(row) else 0
        except RuntimeError as exc:
            print(f"[pay] could not check link {row['link_id']}: {exc}")
    return newly


# ---------------------------------------------------------------- starting a payment
def start_payment(booking):
    """Returns (url, message). url is the Razorpay page to open, or None if nothing needs paying / it failed.
    `booking` is a row from ui.fetch_bookings (so it has ref, due, fare_total)."""
    if not is_configured():
        return None, "Online payment isn't set up yet."
    _ensure_table()
    # pick up a payment that was made but not yet recorded
    sync_booking(booking["id"])
    fresh = db.q1("SELECT COALESCE((SELECT SUM(amount) FROM payments WHERE booking_id=? AND status='paid'),0) AS paid, fare_total "
                  "FROM bookings WHERE id=?", (booking["id"], booking["id"]))
    due = max((fresh["fare_total"] or 0) - fresh["paid"], 0)
    if fresh["fare_total"] is None:
        return None, "The fare for this booking isn't confirmed yet."
    if due <= 0:
        return None, "This booking is already paid. Thank you!"
    # reuse an open link for the same amount; otherwise cancel it and make a new one
    for row in db.q("SELECT * FROM online_payments WHERE booking_id=? AND status='created' ORDER BY id DESC", (booking["id"],)):
        if abs(row["amount"] - due) < 0.01:
            return row["short_url"], ""
        try:
            _call("POST", f"/payment_links/{row['link_id']}/cancel")
        except RuntimeError:
            pass
        db.run("UPDATE online_payments SET status='cancelled' WHERE id=?", (row["id"],))
    cust = db.q1("SELECT full_name, username, email, phone FROM users WHERE id=?", (booking["customer_id"],)) or {}
    payload = {
        "amount": int(round(due * 100)), "currency": "INR", "accept_partial": False,
        "reference_id": f"{booking['ref']}-{int(time.time())}",
        "description": f"GTD Travel booking {booking['ref']}",
        "expire_by": int(time.time()) + LINK_LIFETIME_HOURS * 3600,
        "notify": {"sms": False, "email": False}, "reminder_enable": False,
        "notes": {"booking": booking["ref"]},
    }
    customer = {"name": cust.get("full_name") or cust.get("username") or ""}
    if cust.get("email"):
        customer["email"] = cust["email"]
    if cust.get("phone"):
        customer["contact"] = cust["phone"]
    try:
        try:
            link = _call("POST", "/payment_links", {**payload, "customer": customer})
        except RuntimeError:
            link = _call("POST", "/payment_links", payload)  # retry without customer details
    except RuntimeError as exc:
        print(f"[pay] could not create link for booking {booking['id']}: {exc}")
        return None, f"We couldn't start the payment: {exc}"
    db.run("INSERT INTO online_payments(booking_id,link_id,short_url,amount,created_at) VALUES(?,?,?,?,?)",
           (booking["id"], link["id"], link["short_url"], due, db.now_str()))
    return link["short_url"], ""
