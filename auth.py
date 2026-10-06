"""Passwords, logins, sign-up and password reset. No Streamlit imports."""
import hashlib
import hmac
import os
import re
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

import db
import sms

ITERATIONS = 200_000
ROLE_LABELS = {"customer": "Customer", "vendor": "Taxi vendor", "driver": "Driver", "admin": "Admin"}


# ---------------------------------------------------------------- passwords
def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS).hex()
    return f"pbkdf2${ITERATIONS}${salt}${digest}"


def verify_password(password, stored):
    try:
        _, iters, salt, digest = stored.split("$")
        test = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
        return hmac.compare_digest(test, digest)
    except (ValueError, AttributeError):
        return False


def check_new_password(pw):
    if len(pw) < 8:
        return "Use at least 8 characters."
    if pw.isdigit():
        return "Add some letters, not only numbers."
    return None


# ---------------------------------------------------------------- phone numbers + OTP
OTP_TTL_MIN, OTP_MAX_ATTEMPTS, OTP_RESEND_SECONDS, OTP_MAX_PER_HOUR = 5, 5, 30, 5


def normalize_phone(raw):
    """Returns +E.164 (Indian 10-digit numbers get +91) or None if invalid."""
    s = re.sub(r"[\s\-()]", "", raw or "")
    if re.fullmatch(r"\+\d{8,15}", s):
        return s
    if re.fullmatch(r"(0|91|0091)?[6-9]\d{9}", s):
        return "+91" + s[-10:]
    return None


def mask_phone(phone):
    return phone[:3] + "\u2022" * max(len(phone) - 6, 0) + phone[-3:] if phone else ""


def mask_email(email):
    name, _, domain = (email or "").partition("@")
    return (name[:2] + "***@" + domain) if domain else ""


def _otp_hash(user_id, code):
    return hashlib.sha256(f"{user_id}:{code}".encode()).hexdigest()


def change_phone(user_id, raw):
    """Sets a new number and marks it unverified. Returns an error message or None."""
    phone = normalize_phone(raw)
    if not phone:
        return "Enter a valid mobile number (10 digits, or with a country code like +91...)."
    db.run("UPDATE users SET phone=?, phone_verified=0 WHERE id=?", (phone, user_id))
    return None


def send_otp(user_id):
    """Emails a 6-digit code. Returns (ok, message)."""
    u = db.q1("SELECT * FROM users WHERE id=?", (user_id,))
    if not u or not u["email"]:
        return False, "There is no email address on this account."
    now = db.now()
    last = db.q1("SELECT created_at FROM otp_codes WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
    if last:
        wait = OTP_RESEND_SECONDS - (now - datetime.strptime(last["created_at"], "%Y-%m-%d %H:%M:%S")).total_seconds()
        if wait > 0:
            return False, f"Please wait {int(wait) + 1} seconds before asking for another code."
    hour_ago = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    if db.q1("SELECT COUNT(*) n FROM otp_codes WHERE user_id=? AND created_at>?", (user_id, hour_ago))["n"] >= OTP_MAX_PER_HOUR:
        return False, "Too many codes requested. Please try again in an hour."
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.run_many([
        ("UPDATE otp_codes SET used=1 WHERE user_id=?", (user_id,)),
        ("INSERT INTO otp_codes(user_id,phone,code_hash,expires_at,created_at) VALUES(?,?,?,?,?)",
         (user_id, u["phone"], _otp_hash(user_id, code),
          (now + timedelta(minutes=OTP_TTL_MIN)).strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S"))),
    ])
    try:
        send_email(u["email"], "Your GTD Travel verification code",
                   f"Hello {u['full_name'] or u['username']},\n\nYour verification code is: {code}\n\n"
                   f"It works for {OTP_TTL_MIN} minutes. Don't share it with anyone.\n")
    except Exception as exc:
        print(f"[otp] email failed for user {user_id}: {exc}")
        return False, "We couldn't send the email. Please try again in a moment."
    return True, f"Code sent to {mask_email(u['email'])}. It works for {OTP_TTL_MIN} minutes."


def verify_otp(user_id, code):
    """Returns (ok, message)."""
    code = (code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        return False, "Enter the 6-digit code."
    row = db.q1("SELECT * FROM otp_codes WHERE user_id=? AND used=0 ORDER BY id DESC LIMIT 1", (user_id,))
    if not row:
        return False, "Ask for a code first."
    if row["expires_at"] < db.now_str():
        return False, "That code has expired. Ask for a new one."
    if row["attempts"] >= OTP_MAX_ATTEMPTS:
        return False, "Too many wrong attempts. Ask for a new code."
    if not hmac.compare_digest(row["code_hash"], _otp_hash(user_id, code)):
        db.run("UPDATE otp_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
        left = OTP_MAX_ATTEMPTS - row["attempts"] - 1
        return False, f"Wrong code. {left} attempt(s) left." if left > 0 else "Wrong code. Ask for a new one."
    u = db.q1("SELECT phone FROM users WHERE id=?", (user_id,))
    if not u or u["phone"] != row["phone"]:
        return False, "Your number changed. Ask for a new code."
    db.run_many([("UPDATE otp_codes SET used=1 WHERE user_id=?", (user_id,)),
                 ("UPDATE users SET phone_verified=1 WHERE id=?", (user_id,))])
    return True, "Phone number verified."


# ---------------------------------------------------------------- login
def login(identifier, password, role):
    """Returns (user dict, None) or (None, error message)."""
    identifier = (identifier or "").strip()
    if not identifier or not password:
        return None, "Enter your username or email and your password."
    users = db.q("SELECT * FROM users WHERE username = ? COLLATE NOCASE OR LOWER(email) = LOWER(?)",
                 (identifier, identifier))
    for u in users:
        if not verify_password(password, u["password_hash"]):
            continue
        if not u["active"]:
            return None, "This account is switched off. Please contact GTD."
        if u["role"] != role:
            return None, f"This is not a {ROLE_LABELS[role].lower()} account. Use the correct tab."
        if u["role"] in ("vendor", "driver") and not u["approved"]:
            return None, "Your account is waiting for admin approval."
        return u, None
    return None, "Wrong username/email or password."


def _check_identity(username, email):
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{3,30}", username or ""):
        return "Username: 3-30 letters, numbers or . _ - @"
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or ""):
        return "Enter a valid email address."
    if db.q1("SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,)):
        return "This username is taken."
    if db.q1("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)):
        return "An account with this email already exists."
    return None


def create_user(*, username, email, password, role, full_name="", phone="", company_name="",
                license_no="", vendor_id=None, approved=True, must_change_pw=False):
    """Returns (user_id, None) or (None, error)."""
    err = _check_identity(username.strip(), email.strip()) or check_new_password(password)
    if err:
        return None, err
    phone = phone.strip()
    if role != "admin" or phone:  # everyone except admins needs a valid mobile number
        phone = normalize_phone(phone)
        if not phone:
            return None, "Enter a valid mobile number (10 digits, or with a country code like +91...)."
    uid = db.run(
        "INSERT INTO users(username,email,password_hash,full_name,phone,role,company_name,license_no,vendor_id,approved,must_change_pw)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (username.strip(), email.strip(), hash_password(password), full_name.strip(), phone.strip(), role,
         company_name.strip(), license_no.strip(), vendor_id, int(approved), int(must_change_pw)))
    return uid, None


def create_default_admin():
    if db.q1("SELECT id FROM users WHERE role='admin' LIMIT 1"):
        return
    username = os.environ.get("GTD_ADMIN_USER", "admin")
    password = os.environ.get("GTD_ADMIN_PASSWORD", "admin123")
    db.run("INSERT INTO users(username,email,password_hash,full_name,role,must_change_pw) VALUES(?,?,?,?,?,?)",
           (username, "admin@gtd.example", hash_password(password), "GTD Admin", "admin",
            1 if password == "admin123" else 0))


def change_password(user_id, current, new):
    u = db.q1("SELECT * FROM users WHERE id=?", (user_id,))
    if not u or not verify_password(current, u["password_hash"]):
        return "Your current password is wrong."
    err = check_new_password(new)
    if err:
        return err
    db.run("UPDATE users SET password_hash=?, must_change_pw=0 WHERE id=?", (hash_password(new), user_id))
    return None


def admin_set_password(user_id, new):
    err = check_new_password(new)
    if err:
        return err
    db.run("UPDATE users SET password_hash=?, must_change_pw=0 WHERE id=?", (hash_password(new), user_id))
    return None


# ---------------------------------------------------------------- forgot / reset password
def send_email(to, subject, body):
    """Uses SMTP when GTD_SMTP_HOST is set; otherwise prints the email in the server terminal."""
    host = os.environ.get("GTD_SMTP_HOST")
    if not host:
        print(f"\n--- EMAIL (SMTP not configured) ---\nTo: {to}\nSubject: {subject}\n\n{body}\n-----------------------------\n")
        return
    msg = EmailMessage()
    msg["From"] = os.environ.get("GTD_SMTP_FROM", "GTD Travel <no-reply@gtd.example>")
    msg["To"], msg["Subject"] = to, subject
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.environ.get("GTD_SMTP_PORT", "587")), timeout=20) as s:
        s.starttls()
        if os.environ.get("GTD_SMTP_USER"):
            s.login(os.environ["GTD_SMTP_USER"], os.environ.get("GTD_SMTP_PASSWORD", ""))
        s.send_message(msg)


def _hash_code(code):
    return hashlib.sha256(code.encode()).hexdigest()


def request_reset(email):
    """Emails a one-time code. Says nothing about whether the email exists."""
    for u in db.q("SELECT * FROM users WHERE LOWER(email)=LOWER(?) AND active=1", (email.strip(),)):
        code = secrets.token_urlsafe(6)
        expires = (db.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        db.run("INSERT INTO reset_tokens(user_id, token_hash, expires_at) VALUES(?,?,?)", (u["id"], _hash_code(code), expires))
        send_email(email.strip(), "Your GTD Travel password reset code",
                   f"Hello {u['full_name'] or u['username']},\n\nYour reset code is: {code}\n\n"
                   "It works once and expires in 30 minutes. If you didn't ask for it, ignore this email.\n")


def complete_reset(email, code, new_password):
    """Returns an error message, or None on success."""
    err = check_new_password(new_password)
    if err:
        return err
    now = db.now_str()
    for u in db.q("SELECT * FROM users WHERE LOWER(email)=LOWER(?) AND active=1", (email.strip(),)):
        for t in db.q("SELECT * FROM reset_tokens WHERE user_id=? AND used=0 AND expires_at>?", (u["id"], now)):
            if hmac.compare_digest(t["token_hash"], _hash_code(code.strip())):
                db.run_many([
                    ("UPDATE users SET password_hash=?, must_change_pw=0 WHERE id=?", (hash_password(new_password), u["id"])),
                    ("UPDATE reset_tokens SET used=1 WHERE user_id=?", (u["id"],)),
                ])
                return None
    return "That code is wrong or has expired. Ask for a new one."
