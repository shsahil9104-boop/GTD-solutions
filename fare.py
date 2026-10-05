"""Fare engine: picks the best rate card and prices a trip. No Streamlit imports."""
from decimal import ROUND_HALF_UP, Decimal

import db

NIGHT_START_HOUR, NIGHT_END_HOUR = 22, 6  # night = 22:00 to 05:59


def rupee(x):
    return int(Decimal(str(x)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def num(x):
    return f"{x:g}"


def is_night(dt):
    return dt.hour >= NIGHT_START_HOUR or dt.hour < NIGHT_END_HOUR


def find_rate_card(city_id, trip_type, cab_type_id, journey, pickup_id, drop_id):
    """Most specific wins: exact pair > reversed pair > pickup area > city-wide."""
    sql = "SELECT * FROM rate_cards WHERE active=1 AND city_id=? AND trip_type=? AND cab_type_id=?"
    params = [city_id, trip_type, cab_type_id]
    if trip_type != "local":
        sql += " AND journey=?"
        params.append(journey)
    if pickup_id and drop_id:
        card = (db.q1(sql + " AND pickup_area_id=? AND drop_area_id=?", params + [pickup_id, drop_id])
                or db.q1(sql + " AND pickup_area_id=? AND drop_area_id=? AND bidirectional=1", params + [drop_id, pickup_id]))
        if card:
            return card
    if pickup_id:
        card = db.q1(sql + " AND pickup_area_id=? AND drop_area_id IS NULL", params + [pickup_id])
        if card:
            return card
    return db.q1(sql + " AND pickup_area_id IS NULL AND drop_area_id IS NULL", params)


def calculate_fare(*, city_id, trip_type, journey, cab_type_id, pickup_id, drop_id, pickup_dt,
                   return_date=None, distance_km=None, hours=None):
    card = find_rate_card(city_id, trip_type, cab_type_id, journey, pickup_id, drop_id)
    if not card:
        return {"ok": False, "message": "No rate is set for this route yet. Send the booking and we'll confirm the fare."}

    days = 1
    if journey == "round_trip" and return_date:
        days = max((return_date - pickup_dt.date()).days + 1, 1)

    lines = []
    if card["fixed_fare"] is not None:
        lines.append(("Fixed fare", card["fixed_fare"]))
    else:
        km, hrs = float(distance_km or 0), float(hours or 0)
        if card["per_km"] and not km and not (card["per_hour"] and hrs):
            return {"ok": False, "needs_input": True, "message": "Enter the approximate distance in km to see the fare."}
        if card["base_fare"]:
            lines.append(("Base fare", card["base_fare"]))
        if card["per_km"] and km:
            if journey == "round_trip":
                km *= 2
            billed = max(km, card["min_km"] * days)
            lines.append((f"{num(billed)} km x Rs {num(card['per_km'])}", billed * card["per_km"]))
        if card["per_hour"] and hrs:
            billed_h = max(hrs, card["min_hours"])
            lines.append((f"{num(billed_h)} hr x Rs {num(card['per_hour'])}", billed_h * card["per_hour"]))
        if card["driver_allowance"]:
            label = "Driver allowance" + (f" ({days} days)" if days > 1 else "")
            lines.append((label, card["driver_allowance"] * days))

    lines = [(label, rupee(amt)) for label, amt in lines]
    subtotal = sum(a for _, a in lines)
    if card["night_surcharge_percent"] and is_night(pickup_dt):
        lines.append((f"Night charge ({num(card['night_surcharge_percent'])}%)",
                      rupee(subtotal * card["night_surcharge_percent"] / 100)))
    if card["toll_parking_permit"]:
        lines.append(("Toll / parking / permit", rupee(card["toll_parking_permit"])))

    return {"ok": True, "message": "", "total": sum(a for _, a in lines), "lines": lines, "rate_card_id": card["id"]}
