"""Emails the admin whenever a customer sends a trip request."""
import json
import os
import threading

import auth
import db

ADMIN_EMAIL = os.environ.get("shsahil9894@gmail.com", "bj175424@gmail.com")

SQL = """SELECT b.*, c.name AS city, pa.name AS pickup_area, da.name AS drop_area, ct.name AS cab_type,
  u.full_name, u.username, u.phone, u.email
FROM bookings b JOIN cities c ON c.id=b.city_id JOIN areas pa ON pa.id=b.pickup_area_id
LEFT JOIN areas da ON da.id=b.drop_area_id JOIN cab_types ct ON ct.id=b.cab_type_id JOIN users u ON u.id=b.customer_id
WHERE b.id=?"""


def build_message(booking_id):
    b = db.q1(SQL, (booking_id,))
    ref = f"GTD{b['id']:05d}"
    route = b["pickup_area"] + (f" to {b['drop_area']}" if b["drop_area"] else "")
    if b["drop_address"]:
        route += f" ({b['drop_address']})"
    if b["fare_total"] is not None:
        fare = "\n".join(f"  {label}: Rs {amt:,.0f}" for label, amt in json.loads(b["fare_lines"] or "[]"))
        fare += f"\n  TOTAL: Rs {b['fare_total']:,.0f}"
    else:
        fare = "  No rate set for this route. Please quote the fare."
    body = f"""New trip request {ref}

Customer: {b['full_name'] or b['username']}
Phone: {b['phone']} (verified)
Email: {b['email']}

Trip: {b['trip_type'].title()}, {b['journey'].replace('_', ' ')} in {b['city']}
Route: {route}
Pickup: {b['pickup_dt'][:16]}{(' at ' + b['pickup_address']) if b['pickup_address'] else ''}
Return date: {b['return_date'] or '-'}
Cab: {b['cab_type']}, {b['passengers']} passenger(s)
Distance entered: {b['distance_km'] or '-'} km
Notes: {b['notes'] or '-'}

Fare:
{fare}

Open the Bookings page in the GTD admin area to allocate a vendor and driver.
"""
    return f"New trip request {ref}: {route}", body


def _send(booking_id):
    try:
        subject, body = build_message(booking_id)
        auth.send_email(ADMIN_EMAIL, subject, body)
    except Exception as exc:  # never let an email problem break a booking
        print(f"[notify] Could not email admin about booking {booking_id}: {exc}")


def booking_created(booking_id):
    threading.Thread(target=_send, args=(booking_id,), daemon=True).start()
