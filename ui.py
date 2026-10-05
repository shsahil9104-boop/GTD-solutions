"""Helpers shared by every screen."""
import json
from datetime import date, time, timedelta

import pandas as pd
import streamlit as st

import auth
import db
import fare
import notify
import theme

TRIP_LABELS = {"local": "Local", "outstation": "Outstation", "airport": "Airport"}
JOURNEY_LABELS = {"one_way": "One-way", "round_trip": "Round trip"}
STATUS_LABELS = {"pending": "Pending", "confirmed": "Confirmed", "assigned": "Driver assigned",
                 "ongoing": "On the trip", "completed": "Completed", "cancelled": "Cancelled"}
METHOD_LABELS = {"cash": "Cash", "upi": "UPI", "card": "Card", "bank": "Bank transfer"}
PAY_STATUS_LABELS = {"pending": "Pending", "paid": "Paid", "refunded": "Refunded"}


def inverse(d):
    return {v: k for k, v in d.items()}


def money(x):
    return "-" if x is None or pd.isna(x) else f"\u20b9{x:,.0f}"


def clean(v):
    """data_editor gives NaN/None for blanks."""
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else v


def ref(booking_id):
    return f"GTD{booking_id:05d}"


def flash(msg, kind="success"):
    st.session_state["_flash"] = (kind, msg)


def show_flash():
    if "_flash" in st.session_state:
        kind, msg = st.session_state.pop("_flash")
        getattr(st, kind)(msg)


def goto(page):
    """Switch page. Applied at the top of the next run (before the menu widget exists)."""
    st.session_state["_goto"] = page


# ---------------------------------------------------------------- lookups
def cities():
    return db.q("SELECT c.id, c.name, s.name AS state FROM cities c JOIN states s ON s.id=c.state_id "
                "WHERE c.active=1 ORDER BY c.name")


def areas(city_id):
    return db.q("SELECT * FROM areas WHERE city_id=? AND active=1 ORDER BY is_airport DESC, name", (city_id,))


def cab_types():
    return db.q("SELECT * FROM cab_types WHERE active=1 ORDER BY sort_order, name")


# ---------------------------------------------------------------- bookings
BOOKING_SQL = """
SELECT b.*, c.name AS city, pa.name AS pickup_area, da.name AS drop_area, ct.name AS cab_type,
  cu.username AS customer, cu.full_name AS customer_name, cu.phone AS customer_phone,
  v.username AS vendor, v.company_name AS company_name,
  d.username AS driver, d.full_name AS driver_name, d.phone AS driver_phone,
  veh.reg_no AS vehicle_reg, veh.name AS vehicle_name,
  COALESCE((SELECT SUM(amount) FROM payments p WHERE p.booking_id=b.id AND p.status='paid'),0) AS paid
FROM bookings b
JOIN cities c ON c.id=b.city_id JOIN areas pa ON pa.id=b.pickup_area_id LEFT JOIN areas da ON da.id=b.drop_area_id
JOIN cab_types ct ON ct.id=b.cab_type_id JOIN users cu ON cu.id=b.customer_id
LEFT JOIN users v ON v.id=b.vendor_id LEFT JOIN users d ON d.id=b.driver_id LEFT JOIN vehicles veh ON veh.id=b.vehicle_id
"""


def fetch_bookings(where="", params=(), order="b.pickup_dt DESC"):
    rows = db.q(f"{BOOKING_SQL} {('WHERE ' + where) if where else ''} ORDER BY {order}", params)
    for b in rows:
        b["ref"] = ref(b["id"])
        b["route"] = b["pickup_area"] + (f" to {b['drop_area']}" if b["drop_area"] else
                                         f" to {b['drop_address']}" if b["drop_address"] else "")
        fare_total = b["fare_total"]
        b["due"] = max((fare_total or 0) - b["paid"], 0)
        if fare_total is None:
            b["pay_state"] = "Fare pending"
        elif fare_total > 0 and b["paid"] >= fare_total:
            b["pay_state"] = "Paid"
        else:
            b["pay_state"] = "Part paid" if b["paid"] > 0 else "Unpaid"
    return rows


def mark_cash_collected(booking_id):
    b = db.q1("SELECT fare_total FROM bookings WHERE id=?", (booking_id,))
    paid = db.q1("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE booking_id=? AND status='paid'", (booking_id,))["s"]
    due = max((b["fare_total"] or 0) - paid, 0)
    stmts = [("DELETE FROM payments WHERE booking_id=? AND status='pending'", (booking_id,))]
    if due > 0:
        stmts.append(("INSERT INTO payments(booking_id,amount,method,status,paid_at) VALUES(?,?,?,?,?)",
                      (booking_id, due, "cash", "paid", db.now_str())))
    db.run_many(stmts)
    return due


def set_fare(booking_id, total, lines=None, rate_card_id=None):
    """Update a booking's fare and keep its pending payment in step."""
    stmts = [("UPDATE bookings SET fare_total=?, fare_lines=COALESCE(?,fare_lines), rate_card_id=COALESCE(?,rate_card_id) WHERE id=?",
              (total, json.dumps(lines) if lines is not None else None, rate_card_id, booking_id))]
    if total is not None:
        stmts.append(("UPDATE payments SET amount=? WHERE booking_id=? AND status='pending'", (total, booking_id)))
    db.run_many(stmts)


def show_fare(res):
    if not res["ok"]:
        st.info(res["message"])
        return
    theme.fare_card(money(res["total"]), [(l, money(a)) for l, a in res["lines"]], "Final fare is confirmed by GTD after booking.")


def booking_detail(b):
    """Full details of one booking (used inside expanders)."""
    st.markdown(theme.badge(STATUS_LABELS[b["status"]], b["status"]), unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Trip:** {TRIP_LABELS[b['trip_type']]}, {JOURNEY_LABELS[b['journey']]} in {b['city']}")
        st.write(f"**Route:** {b['route']}")
        st.write(f"**Pickup:** {b['pickup_dt'][:16]}" + (f", {b['pickup_address']}" if b["pickup_address"] else ""))
        if b["drop_address"]:
            st.write(f"**Destination:** {b['drop_address']}")
        if b["return_date"]:
            st.write(f"**Return date:** {b['return_date']}")
        st.write(f"**Cab:** {b['cab_type']}, {b['passengers']} passenger(s)")
        if b["distance_km"]:
            st.write(f"**Distance entered:** {b['distance_km']:g} km (one way)")
        if b["notes"]:
            st.write(f"**Notes:** {b['notes']}")
    with c2:
        if b["fare_total"] is not None:
            for ln in json.loads(b["fare_lines"] or "[]"):
                st.write(f"{ln[0]}: {money(ln[1])}")
            st.write(f"**Total: {money(b['fare_total'])}**  ({b['pay_state']}, paid {money(b['paid'])}, due {money(b['due'])})")
        else:
            st.write("**Fare:** GTD will quote this shortly.")
        if b["vendor"]:
            st.write(f"**Operator:** {b['company_name'] or b['vendor']}")
        if b["driver"]:
            st.write(f"**Driver:** {b['driver_name'] or b['driver']} {b['driver_phone'] or ''}")
        if b["vehicle_reg"]:
            st.write(f"**Vehicle:** {b['vehicle_name']}, {b['vehicle_reg']}")
        if b["admin_note"]:
            st.info(f"Message from GTD: {b['admin_note']}")


# ---------------------------------------------------------------- booking form with live fare
def booking_form(user=None):
    city_rows, cabs = cities(), cab_types()
    if not city_rows or not cabs:
        st.info("No cities or cab types are set up yet.")
        return
    city_label = {c["id"]: f"{c['name']}, {c['state']}" for c in city_rows}
    cab_label = {c["id"]: f"{c['name']} ({c['seats']} seats)" for c in cabs}
    cab_seats = {c["id"]: c["seats"] for c in cabs}
    today = db.now().date()

    left, right = st.columns([3, 2], gap="large")
    with left:
        city_id = st.selectbox("City", list(city_label), format_func=city_label.get, key="bk_city")
        trip_type = st.radio("Trip type", list(TRIP_LABELS), format_func=TRIP_LABELS.get, horizontal=True, key="bk_type")
        journey = "one_way"
        if trip_type != "local":
            journey = st.radio("One-way or round trip", list(JOURNEY_LABELS), format_func=JOURNEY_LABELS.get,
                               horizontal=True, key="bk_journey")
        area_rows = areas(city_id)
        aname = {a["id"]: a["name"] for a in area_rows}
        aair = {a["id"]: bool(a["is_airport"]) for a in area_rows}
        c1, c2 = st.columns(2)
        pickup_id = c1.selectbox("Pickup area", list(aname), format_func=aname.get, key=f"bk_pickup_{city_id}")
        drop_id = c2.selectbox("Drop area", [None] + list(aname),
                               format_func=lambda i: "Not needed" if i is None else aname[i], key=f"bk_drop_{city_id}")
        pickup_address = st.text_input("Pickup address / landmark", key="bk_paddr")
        drop_address = st.text_input("Drop address / destination", key="bk_daddr")
        cab_id = st.selectbox("Cab type", list(cab_label), format_func=cab_label.get, key="bk_cab")
        d1, d2 = st.columns(2)
        pdate = d1.date_input("Pickup date", value=today + timedelta(days=1), min_value=today, key="bk_date")
        ptime = d2.time_input("Pickup time", value=time(9, 0), step=900, key="bk_time")
        return_date = None
        if journey == "round_trip":
            return_date = st.date_input("Return date", value=pdate, min_value=pdate, key=f"bk_return_{pdate}")
        e1, e2, e3 = st.columns(3)
        passengers = e1.number_input("Passengers", min_value=1, max_value=60, value=1, key="bk_pax")
        distance = e2.number_input("Approx. distance (km, one way)", min_value=0.0, step=1.0, key="bk_km")
        hours = e3.number_input("Hours (local package)", min_value=0.0, step=0.5, key="bk_hrs") if trip_type == "local" else None
        notes = st.text_area("Notes", key="bk_notes", height=80)

    from datetime import datetime
    pickup_dt = datetime.combine(pdate, ptime)
    errors = []
    if pickup_id is None:
        errors.append("Choose a pickup area.")
    if pickup_id and drop_id and pickup_id == drop_id:
        errors.append("Pickup and drop can't be the same area.")
    if trip_type == "airport":
        if not drop_id:
            errors.append("Choose the other end of your airport trip.")
        elif pickup_id and not (aair.get(pickup_id) or aair.get(drop_id)):
            errors.append("One of the two areas must be the airport.")
    if trip_type == "outstation" and not drop_address.strip():
        errors.append("Enter your destination.")
    if pickup_dt < db.now():
        errors.append("Pickup time must be in the future.")
    if passengers > cab_seats.get(cab_id, 99):
        errors.append(f"This cab seats {cab_seats[cab_id]}. Choose a bigger cab or fewer passengers.")

    result = None
    with right:
        st.subheader("Your fare")
        if errors:
            for e in errors:
                st.warning(e)
        else:
            result = fare.calculate_fare(city_id=city_id, trip_type=trip_type, journey=journey, cab_type_id=cab_id,
                                         pickup_id=pickup_id, drop_id=drop_id, pickup_dt=pickup_dt,
                                         return_date=return_date, distance_km=distance, hours=hours)
            show_fare(result)

        if user is None:
            st.info("Log in with a customer account to send this booking.")
        elif user["role"] != "customer":
            st.info("Only customer accounts can send bookings.")
        elif st.button("Send booking", type="primary", disabled=bool(errors), use_container_width=True):
            ok = result and result["ok"]
            bid = db.run(
                "INSERT INTO bookings(customer_id,city_id,trip_type,journey,pickup_area_id,drop_area_id,pickup_address,"
                "drop_address,cab_type_id,pickup_dt,return_date,passengers,distance_km,hours,notes,rate_card_id,fare_total,fare_lines)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (user["id"], city_id, trip_type, journey, pickup_id, drop_id, pickup_address.strip(), drop_address.strip(),
                 cab_id, pickup_dt.strftime("%Y-%m-%d %H:%M"), return_date.isoformat() if return_date else None,
                 int(passengers), distance or None, hours or None, notes.strip(),
                 result["rate_card_id"] if ok else None, result["total"] if ok else None,
                 json.dumps(result["lines"]) if ok else "[]"))
            if ok:
                db.run("INSERT INTO payments(booking_id, amount) VALUES(?,?)", (bid, result["total"]))
            notify.booking_created(bid)  # emails the admin in the background
            flash(f"Booking {ref(bid)} received. Our team has been notified.")
            goto("My bookings")
            st.rerun()


# ---------------------------------------------------------------- account
def account_page(user):
    st.header("My account")
    st.write(f"**{user['full_name'] or user['username']}** ({auth.ROLE_LABELS[user['role']]}), {user['email']}")
    if user["must_change_pw"]:
        st.warning("You are using a starter password. Please choose a new one.")
    if user["phone"]:
        st.write(f"**Phone:** {user['phone']}  " + ("(verified)" if user["phone_verified"] else "(not verified)"))
    with st.expander("Change my phone number"):
        with st.form("chphone_acc"):
            new_phone = st.text_input("New mobile number", help="You'll need to verify it with a code.")
            if st.form_submit_button("Update number"):
                err = auth.change_phone(user["id"], new_phone)
                if err:
                    st.error(err)
                else:
                    st.rerun()
    with st.form("chpw"):
        cur = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password", help="At least 8 characters.")
        new2 = st.text_input("Repeat new password", type="password")
        if st.form_submit_button("Change password", type="primary"):
            if new != new2:
                st.error("The two new passwords don't match.")
            elif (err := auth.change_password(user["id"], cur, new)):
                st.error(err)
            else:
                st.session_state["user"] = db.q1("SELECT * FROM users WHERE id=?", (user["id"],))
                st.success("Password changed.")
