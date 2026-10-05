"""Sends text messages. Uses Twilio when configured; otherwise prints the message in the server terminal (dev mode)."""
import base64
import json
import os
import urllib.parse
import urllib.request


def is_configured():
    return all(os.environ.get(k) for k in ("GTD_TWILIO_SID", "GTD_TWILIO_TOKEN", "GTD_TWILIO_FROM"))


def send_sms(to, text):
    """to: phone in +E.164 format. Raises on failure."""
    if not is_configured():
        print(f"\n--- SMS (Twilio not configured) ---\nTo: {to}\n{text}\n-----------------------------------\n")
        return
    sid, token = os.environ["GTD_TWILIO_SID"], os.environ["GTD_TWILIO_TOKEN"]
    data = urllib.parse.urlencode({"To": to, "From": os.environ["GTD_TWILIO_FROM"], "Body": text}).encode()
    req = urllib.request.Request(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data=data)
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode())
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status >= 300:
            raise RuntimeError(json.loads(resp.read().decode()).get("message", "SMS failed"))
