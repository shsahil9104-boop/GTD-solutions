"""Admin screens: dashboard, bookings, rate cards, locations, cab types, people, payments, reports."""
from datetime import timedelta

import pandas as pd
import streamlit as st

import auth
import db
import pay
import ui
from ui import clean, inverse, money


# ---------------------------------------------------------------- generic editable table
def _norm(kind, v):
    v = clean(v)
    if kind == "bool":
        return int(bool(v))
    if kind == "int":
        return int(v or 0)
    if kind == "float":
        return float(v or 0)
    if kind == "float?":
        return None if v is None else float(v)
    return str(v or "").strip()


def table_editor(key, rows, columns, table, kinds, editable, config=None, after=None):
    """Show rows in an editable grid and save changed cells.
    columns: {db_col: label}; kinds: {db_col: bool|int|float|float?|text}; editable: list of db_cols."""
    if not rows:
        st.info("Nothing here yet.")
        return
    df = pd.DataFrame([{label: r[col] for col, label in columns.items()} for r in rows])
    for col, label in columns.items():
        if kinds.get(col) == "bool":
            df[label] = df[label].astype(bool)
    edited = st.data_editor(df, hide_index=True, use_container_width=True, key=key, column_config=config or {},
                            disabled=[label for col, label in columns.items() if col not in editable])
    if st.button("Save changes", key=f"{key}_save", type="primary"):
        changed = 0
        for i, r in enumerate(rows):
            sets, vals = [], []
            for col in editable:
                new, old = _norm(kinds[col], edited.iloc[i][columns[col]]), _norm(kinds[col], r[col])
                if new != old:
                    sets.append(f"{col}=?")
                    vals.append(new)
            if sets:
                db.run(f"UPDATE {table} SET {', '.join(sets)} WHERE id=?", (*vals, r["id"]))
                changed += 1
        if after:
            after()
        ui.flash(f"Saved {changed} row(s)." if changed else "No changes to save.", "success" if changed else "info")
        st.rerun()


# ---------------------------------------------------------------- dashboard
def dashboard():
    user = st.session_state["user"]
    st.header("Dashboard")
    ui.show_flash()
    if user["must_change_pw"]:
        st.warning("You are still using the starter admin password. Open **My account** and change it now.")
    today = db.now().strftime("%Y-%m-%d")
    n = lambda sql, p=(): db.q1(sql, p)["n"]
    collected = db.q1("SELECT COALESCE(SUM(p.amount),0) n FROM payments p JOIN bookings b ON b.id=p.booking_id "
                      "WHERE p.status='paid' AND b.status!='cancelled'")["n"]
    booked = db.q1("SELECT COALESCE(SUM(fare_total),0) n FROM bookings WHERE status!='cancelled'")["n"]
    c = st.columns(6)
    c[0].metric("Trips today", n("SELECT COUNT(*) n FROM bookings WHERE date(pickup_dt)=? AND status!='cancelled'", (today,)))
    c[1].metric("Waiting for you", n("SELECT COUNT(*) n FROM bookings WHERE status='pending'"))
    c[2].metric("On the road now", n("SELECT COUNT(*) n FROM bookings WHERE status='ongoing'"))
    c[3].metric("Collected", money(collected))
    c[4].metric("Still to collect", money(max(booked - collected, 0)))
    c[5].metric("Vendors to approve", n("SELECT COUNT(*) n FROM users WHERE role='vendor' AND approved=0"))
    st.subheader("Latest bookings")
    rows = ui.fetch_bookings(order="b.id DESC")[:10]
    if rows:
        st.dataframe(pd.DataFrame([{"Ref": b["ref"], "Customer": b["customer"], "Trip": b["route"], "Pickup": b["pickup_dt"][:16],
                                    "Cab": b["cab_type"], "Fare": money(b["fare_total"]), "Vendor": b["vendor"] or "-",
                                    "Status": ui.STATUS_LABELS[b["status"]]} for b in rows]),
                     hide_index=True, use_container_width=True)
    else:
        st.info("No bookings yet.")
    st.caption("Use the menu on the left to manage rates, locations, cab types, people, payments and reports.")


# ---------------------------------------------------------------- bookings
def bookings():
    st.header("Bookings")
    ui.show_flash()
    f1, f2 = st.columns([3, 2])
    statuses = f1.multiselect("Status", list(ui.STATUS_LABELS), default=list(ui.STATUS_LABELS), format_func=ui.STATUS_LABELS.get)
    text = f2.text_input("Search customer, area or ref").strip().lower()
    rows = [b for b in ui.fetch_bookings(order="b.pickup_dt DESC") if b["status"] in statuses
            and (not text or text in f"{b['ref']} {b['customer']} {b['route']}".lower())]
    if not rows:
        st.info("No bookings match.")
        return
    vendors = db.q("SELECT id, username, company_name FROM users WHERE role='vendor' AND approved=1 AND active=1")
    drivers = db.q("SELECT id, username, full_name FROM users WHERE role='driver' AND active=1")
    vl = {v["id"]: f"{v['company_name'] or v['username']} ({v['username']})" for v in vendors}
    dl = {d["id"]: f"{d['full_name'] or d['username']} ({d['username']})" for d in drivers}
    srev = inverse(ui.STATUS_LABELS)
    df = pd.DataFrame([{"Ref": b["ref"], "Customer": b["customer"], "Trip": b["route"], "Pickup": b["pickup_dt"][:16],
                        "Cab": b["cab_type"], "Fare": b["fare_total"], "Payment": b["pay_state"],
                        "Vendor": vl.get(b["vendor_id"]), "Driver": dl.get(b["driver_id"]),
                        "Status": ui.STATUS_LABELS[b["status"]], "Message to customer": b["admin_note"]} for b in rows])
    edited = st.data_editor(
        df, hide_index=True, use_container_width=True, key="adm_bookings",
        disabled=["Ref", "Customer", "Trip", "Pickup", "Cab", "Payment"],
        column_config={
            "Fare": st.column_config.NumberColumn("Fare (Rs)", min_value=0, format="%.0f"),
            "Vendor": st.column_config.SelectboxColumn(options=list(vl.values())),
            "Driver": st.column_config.SelectboxColumn(options=list(dl.values())),
            "Status": st.column_config.SelectboxColumn(options=list(ui.STATUS_LABELS.values()), required=True),
        })
    st.caption("Edit fare, vendor, driver, status or message in the grid, then save.")
    if st.button("Save changes", type="primary"):
        vrev, drev, changed = inverse(vl), inverse(dl), 0
        for i, b in enumerate(rows):
            e = edited.iloc[i]
            fare_new, fare_old = clean(e["Fare"]), b["fare_total"]
            vendor, driver = vrev.get(clean(e["Vendor"])), drev.get(clean(e["Driver"]))
            status, note = srev[e["Status"]], str(clean(e["Message to customer"]) or "")
            if (vendor, driver, status, note) != (b["vendor_id"], b["driver_id"], b["status"], b["admin_note"]):
                db.run("UPDATE bookings SET vendor_id=?, driver_id=?, status=?, admin_note=? WHERE id=?",
                       (vendor, driver, status, note, b["id"]))
                changed += 1
            if fare_new != fare_old and not (fare_new is None and fare_old is None):
                ui.set_fare(b["id"], None if fare_new is None else float(fare_new))
                if fare_new is not None and not db.q1("SELECT id FROM payments WHERE booking_id=?", (b["id"],)):
                    db.run("INSERT INTO payments(booking_id, amount) VALUES(?,?)", (b["id"], float(fare_new)))
                changed += 1
        ui.flash(f"Saved {changed} change(s)." if changed else "No changes to save.")
        st.rerun()

    with st.expander("Recalculate fares from the current rate cards"):
        st.write("Use this after changing rates. It rewrites the fare on the bookings you pick.")
        pick = st.multiselect("Bookings", [b["ref"] for b in rows])
        if st.button("Recalculate selected") and pick:
            import fare
            from datetime import datetime
            done = 0
            for b in rows:
                if b["ref"] not in pick:
                    continue
                res = fare.calculate_fare(
                    city_id=b["city_id"], trip_type=b["trip_type"], journey=b["journey"], cab_type_id=b["cab_type_id"],
                    pickup_id=b["pickup_area_id"], drop_id=b["drop_area_id"],
                    pickup_dt=datetime.strptime(b["pickup_dt"][:16], "%Y-%m-%d %H:%M"),
                    return_date=datetime.strptime(b["return_date"], "%Y-%m-%d").date() if b["return_date"] else None,
                    distance_km=b["distance_km"], hours=b["hours"])
                if res["ok"]:
                    ui.set_fare(b["id"], res["total"], res["lines"], res["rate_card_id"])
                    done += 1
            ui.flash(f"Recalculated {done} of {len(pick)} booking(s).")
            st.rerun()


# ---------------------------------------------------------------- rate cards
RATE_FIELDS = [  # (db column, label, nullable)
    ("fixed_fare", "Fixed fare", True), ("base_fare", "Base fare", False), ("per_km", "Per km", False),
    ("per_hour", "Per hour", False), ("min_km", "Min km/day", False), ("min_hours", "Min hours", False),
    ("driver_allowance", "Driver allowance/day", False), ("toll_parking_permit", "Toll/parking/permit", False),
    ("night_surcharge_percent", "Night %", False)]


def rate_cards():
    st.header("Rate cards")
    ui.show_flash()
    st.caption("Fares are picked in this order: exact pickup-to-drop route, the same route reversed, pickup area, then city-wide.")
    city_rows = db.q("SELECT c.id, c.name, s.name AS state FROM cities c JOIN states s ON s.id=c.state_id ORDER BY c.name")
    cab_rows = db.q("SELECT id, name FROM cab_types ORDER BY sort_order, name")
    if not city_rows or not cab_rows:
        st.info("Add a city and a cab type first (Locations and Cab types in the menu).")
        return
    cl = {c["id"]: f"{c['name']}, {c['state']}" for c in city_rows}
    cabl = {c["id"]: c["name"] for c in cab_rows}

    f = st.columns(4)
    fc = f[0].selectbox("City", [None] + list(cl), format_func=lambda i: "All cities" if i is None else cl[i])
    ft = f[1].selectbox("Trip type", [None] + list(ui.TRIP_LABELS), format_func=lambda i: "All types" if i is None else ui.TRIP_LABELS[i])
    fcab = f[2].selectbox("Cab type", [None] + list(cabl), format_func=lambda i: "All cabs" if i is None else cabl[i])
    inactive = f[3].checkbox("Show switched-off cards")
    where, params = ["1=1"], []
    for col, val in (("r.city_id", fc), ("r.trip_type", ft), ("r.cab_type_id", fcab)):
        if val is not None:
            where.append(f"{col}=?")
            params.append(val)
    if not inactive:
        where.append("r.active=1")
    rows = db.q(f"""SELECT r.*, c.name AS city, ct.name AS cab, pa.name AS pickup, da.name AS drop_
        FROM rate_cards r JOIN cities c ON c.id=r.city_id JOIN cab_types ct ON ct.id=r.cab_type_id
        LEFT JOIN areas pa ON pa.id=r.pickup_area_id LEFT JOIN areas da ON da.id=r.drop_area_id
        WHERE {' AND '.join(where)} ORDER BY c.name, r.trip_type, ct.sort_order, pa.name, da.name""", params)

    st.subheader(f"{len(rows)} rate card(s)")
    if rows:
        df = pd.DataFrame([{"ID": r["id"], "City": r["city"], "Trip type": ui.TRIP_LABELS[r["trip_type"]],
                            "Journey": ui.JOURNEY_LABELS[r["journey"]] if r["trip_type"] != "local" else "-",
                            "Cab": r["cab"], "Pickup area": r["pickup"] or "Any", "Drop area": r["drop_"] or "Any",
                            **{label: r[col] for col, label, _ in RATE_FIELDS},
                            "Works both ways": bool(r["bidirectional"]), "Active": bool(r["active"]), "Delete": False}
                           for r in rows])
        cfg = {label: st.column_config.NumberColumn(label, min_value=0, format="%.2f") for _, label, _ in RATE_FIELDS}
        edited = st.data_editor(df, hide_index=True, use_container_width=True, key="rc_editor", column_config=cfg,
                                disabled=["ID", "City", "Trip type", "Journey", "Cab", "Pickup area", "Drop area"])
        if st.button("Save rate changes", type="primary"):
            changed = deleted = 0
            for i, r in enumerate(rows):
                e = edited.iloc[i]
                if e["Delete"]:
                    db.run_many([("UPDATE bookings SET rate_card_id=NULL WHERE rate_card_id=?", (r["id"],)),
                                 ("DELETE FROM rate_cards WHERE id=?", (r["id"],))])
                    deleted += 1
                    continue
                sets, vals = [], []
                for col, label, nullable in RATE_FIELDS:
                    new = _norm("float?" if nullable else "float", e[label])
                    if new != _norm("float?" if nullable else "float", r[col]):
                        sets.append(f"{col}=?")
                        vals.append(new)
                for col, label in (("bidirectional", "Works both ways"), ("active", "Active")):
                    if int(bool(e[label])) != r[col]:
                        sets.append(f"{col}=?")
                        vals.append(int(bool(e[label])))
                if sets:
                    db.run(f"UPDATE rate_cards SET {', '.join(sets)}, updated_at=CURRENT_TIMESTAMP WHERE id=?", (*vals, r["id"]))
                    changed += 1
            ui.flash(f"Updated {changed} and deleted {deleted} rate card(s).")
            st.rerun()

        with st.expander("Change all shown rates by a percentage"):
            pct = st.number_input("Percent change (negative to reduce)", min_value=-90.0, max_value=300.0, value=5.0, step=1.0)
            ok = st.checkbox(f"Yes, change {len(rows)} shown rate card(s) by {pct:+g}%")
            if st.button("Apply percentage", disabled=not ok):
                factor = 1 + pct / 100
                cols = ["fixed_fare", "base_fare", "per_km", "per_hour", "driver_allowance", "toll_parking_permit"]
                sets = ", ".join(f"{c}=ROUND({c}*?,2)" for c in cols)
                for r in rows:
                    db.run(f"UPDATE rate_cards SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=?", (*([factor] * len(cols)), r["id"]))
                ui.flash(f"Changed {len(rows)} rate card(s) by {pct:+g}%.")
                st.rerun()

    st.subheader("Add a rate card")
    city_id = st.selectbox("City for the new card", list(cl), format_func=cl.get, key="rc_new_city")
    area_rows = ui.areas(city_id)
    al = {a["id"]: a["name"] for a in area_rows}
    with st.form("rc_new"):
        a, b, c_ = st.columns(3)
        trip = a.selectbox("Trip type", list(ui.TRIP_LABELS), format_func=ui.TRIP_LABELS.get)
        journey = b.selectbox("Journey (not used for local)", list(ui.JOURNEY_LABELS), format_func=ui.JOURNEY_LABELS.get)
        cab = c_.selectbox("Cab type", list(cabl), format_func=cabl.get)
        p, d, both = st.columns(3)
        pickup = p.selectbox("Pickup area (leave 'Any' for city-wide)", [None] + list(al), format_func=lambda i: "Any" if i is None else al[i])
        drop = d.selectbox("Drop area", [None] + list(al), format_func=lambda i: "Any" if i is None else al[i])
        bidir = both.checkbox("Also apply when pickup and drop are swapped", value=True)
        r1 = st.columns(5)
        fixed = r1[0].number_input("Fixed fare (0 = none)", min_value=0.0, step=10.0)
        base = r1[1].number_input("Base fare", min_value=0.0, step=10.0)
        perkm = r1[2].number_input("Per-km rate", min_value=0.0, step=1.0)
        perhr = r1[3].number_input("Per-hour rate", min_value=0.0, step=10.0)
        night = r1[4].number_input("Night surcharge %", min_value=0.0, max_value=100.0, step=1.0)
        r2 = st.columns(4)
        minkm = r2[0].number_input("Minimum km (per day)", min_value=0.0, step=10.0)
        minhr = r2[1].number_input("Minimum hours", min_value=0.0, step=1.0)
        allow = r2[2].number_input("Driver allowance (per day)", min_value=0.0, step=50.0)
        toll = r2[3].number_input("Toll / parking / permit", min_value=0.0, step=10.0)
        if st.form_submit_button("Add rate card", type="primary"):
            if drop and not pickup:
                st.error("Choose a pickup area when you choose a drop area.")
            elif fixed == 0 and perkm == 0 and perhr == 0 and base == 0:
                st.error("Set a fixed fare, a base fare, or a per-km / per-hour rate.")
            elif db.q1("SELECT id FROM rate_cards WHERE city_id=? AND trip_type=? AND journey=? AND cab_type_id=? "
                       "AND pickup_area_id IS ? AND drop_area_id IS ?",
                       (city_id, trip, "one_way" if trip == "local" else journey, cab, pickup, drop)):
                st.error("A rate card already exists for this exact city, trip, cab and route. Edit it in the table above.")
            else:
                db.run("INSERT INTO rate_cards(city_id,trip_type,journey,cab_type_id,pickup_area_id,drop_area_id,bidirectional,"
                       "fixed_fare,base_fare,per_km,per_hour,min_km,min_hours,driver_allowance,toll_parking_permit,night_surcharge_percent)"
                       " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (city_id, trip, "one_way" if trip == "local" else journey, cab, pickup, drop, int(bidir),
                        fixed or None, base, perkm, perhr, minkm, minhr, allow, toll, night))
                ui.flash("Rate card added.")
                st.rerun()


# ---------------------------------------------------------------- locations
def locations():
    st.header("Locations")
    ui.show_flash()
    t_state, t_city, t_area = st.tabs(["States", "Cities", "Areas / localities"])

    with t_state:
        st.dataframe(pd.DataFrame(db.q("SELECT id AS ID, name AS State FROM states ORDER BY name")), hide_index=True)
        with st.form("new_state", clear_on_submit=True):
            name = st.text_input("New state")
            if st.form_submit_button("Add state") and name.strip():
                if db.q1("SELECT id FROM states WHERE name=? COLLATE NOCASE", (name.strip(),)):
                    st.error("This state already exists.")
                else:
                    db.run("INSERT INTO states(name) VALUES(?)", (name.strip(),))
                    ui.flash("State added.")
                    st.rerun()

    with t_city:
        states = db.q("SELECT * FROM states ORDER BY name")
        if not states:
            st.info("Add a state first.")
        else:
            sl = {s["id"]: s["name"] for s in states}
            rows = db.q("SELECT c.*, s.name AS state FROM cities c JOIN states s ON s.id=c.state_id ORDER BY s.name, c.name")
            table_editor("ed_cities", rows, {"id": "ID", "state": "State", "name": "City", "active": "Active"}, "cities",
                         {"name": "text", "active": "bool"}, ["name", "active"])
            with st.form("new_city", clear_on_submit=True):
                s = st.selectbox("State", list(sl), format_func=sl.get)
                name = st.text_input("New city")
                if st.form_submit_button("Add city") and name.strip():
                    if db.q1("SELECT id FROM cities WHERE state_id=? AND name=? COLLATE NOCASE", (s, name.strip())):
                        st.error("This city already exists in that state.")
                    else:
                        db.run("INSERT INTO cities(state_id,name) VALUES(?,?)", (s, name.strip()))
                        ui.flash("City added.")
                        st.rerun()

    with t_area:
        cities = db.q("SELECT c.id, c.name, s.name AS state FROM cities c JOIN states s ON s.id=c.state_id ORDER BY c.name")
        if not cities:
            st.info("Add a city first.")
        else:
            cl = {c["id"]: f"{c['name']}, {c['state']}" for c in cities}
            cid = st.selectbox("City", list(cl), format_func=cl.get, key="loc_city")
            rows = db.q("SELECT * FROM areas WHERE city_id=? ORDER BY is_airport DESC, name", (cid,))
            table_editor(f"ed_areas_{cid}", rows, {"id": "ID", "name": "Area / locality", "is_airport": "Airport point", "active": "Active"},
                         "areas", {"name": "text", "is_airport": "bool", "active": "bool"}, ["name", "is_airport", "active"])
            with st.form("new_area", clear_on_submit=True):
                name = st.text_input("New area / locality")
                air = st.checkbox("This is an airport pickup/drop point")
                if st.form_submit_button("Add area") and name.strip():
                    if db.q1("SELECT id FROM areas WHERE city_id=? AND name=? COLLATE NOCASE", (cid, name.strip())):
                        st.error("This area already exists in that city.")
                    else:
                        db.run("INSERT INTO areas(city_id,name,is_airport) VALUES(?,?,?)", (cid, name.strip(), int(air)))
                        ui.flash("Area added.")
                        st.rerun()
    st.caption("Places can be switched off but not deleted, so old bookings and rate cards stay intact.")


# ---------------------------------------------------------------- cab types
def cab_types_page():
    st.header("Cab types")
    ui.show_flash()
    rows = db.q("SELECT * FROM cab_types ORDER BY sort_order, name")
    table_editor("ed_cabs", rows, {"id": "ID", "name": "Name", "seats": "Seats", "description": "Description",
                                   "sort_order": "Order", "active": "Active"}, "cab_types",
                 {"name": "text", "seats": "int", "description": "text", "sort_order": "int", "active": "bool"},
                 ["name", "seats", "description", "sort_order", "active"])
    with st.form("new_cab", clear_on_submit=True):
        st.subheader("Add a cab type")
        a, b, c = st.columns(3)
        name, seats, order = a.text_input("Name (e.g. Premium)"), b.number_input("Seats", 1, 60, 4), c.number_input("Order", 0, 99, 5)
        desc = st.text_input("Description")
        if st.form_submit_button("Add cab type", type="primary") and name.strip():
            if db.q1("SELECT id FROM cab_types WHERE name=? COLLATE NOCASE", (name.strip(),)):
                st.error("This cab type already exists.")
            else:
                db.run("INSERT INTO cab_types(name,seats,description,sort_order) VALUES(?,?,?,?)",
                       (name.strip(), int(seats), desc.strip(), int(order)))
                ui.flash("Cab type added.")
                st.rerun()


# ---------------------------------------------------------------- people
def people():
    me = st.session_state["user"]
    st.header("People and logins")
    ui.show_flash()
    role = st.radio("Show", list(auth.ROLE_LABELS), format_func=lambda r: auth.ROLE_LABELS[r] + "s", horizontal=True)
    rows = db.q("SELECT u.*, v.username AS operator FROM users u LEFT JOIN users v ON v.id=u.vendor_id WHERE u.role=? ORDER BY u.id", (role,))
    cols = {"id": "ID", "full_name": "Name", "username": "Username", "email": "Email", "phone": "Phone"}
    if role == "vendor":
        cols["company_name"] = "Company"
    if role == "driver":
        cols.update(license_no="Licence", operator="Operator")
    cols.update(approved="Approved", active="Active")
    table_editor(f"ed_people_{role}", rows, cols, "users",
                 {"full_name": "text", "approved": "bool", "active": "bool"},
                 ["full_name", "approved", "active"],
                 after=lambda: db.run("UPDATE users SET active=1, approved=1 WHERE id=?", (me["id"],)))
    st.caption("Vendors can't log in until Approved is ticked. Untick Active to switch an account off.")

    everyone = db.q("SELECT id, username, role FROM users ORDER BY username")
    ul = {u["id"]: f"{u['username']} ({u['role']})" for u in everyone}
    c1, c2 = st.columns(2)
    with c1, st.form("reset_pw", clear_on_submit=True):
        st.subheader("Reset a password")
        uid = st.selectbox("User", list(ul), format_func=ul.get)
        pw = st.text_input("New password", type="password", help="At least 8 characters. Tell the user to change it.")
        if st.form_submit_button("Set password", type="primary"):
            err = auth.admin_set_password(uid, pw)
            if err:
                st.error(err)
            else:
                db.run("UPDATE users SET must_change_pw=1 WHERE id=?", (uid,))
                st.success("Password changed.")
    vendors = db.q("SELECT id, username, company_name FROM users WHERE role='vendor' AND approved=1")
    vl = {v["id"]: f"{v['company_name'] or v['username']}" for v in vendors}
    with c2, st.form("change_role", clear_on_submit=True):
        st.subheader("Change a user's role")
        uid2 = st.selectbox("User", list(ul), format_func=ul.get, key="cr_user")
        new_role = st.selectbox("New role", list(auth.ROLE_LABELS), format_func=auth.ROLE_LABELS.get)
        op = st.selectbox("Operator (for drivers)", [None] + list(vl), format_func=lambda i: "-" if i is None else vl[i])
        if st.form_submit_button("Change role"):
            if uid2 == me["id"]:
                st.error("You can't change your own role.")
            elif new_role == "driver" and not op:
                st.error("Choose the operator this driver works for.")
            else:
                db.run("UPDATE users SET role=?, vendor_id=?, approved=1 WHERE id=?", (new_role, op if new_role == "driver" else None, uid2))
                ui.flash("Role changed.")
                st.rerun()

    with st.expander("Add a user"):
        with st.form("add_user", clear_on_submit=True):
            r = st.selectbox("Role", list(auth.ROLE_LABELS), format_func=auth.ROLE_LABELS.get, key="au_role")
            a, b = st.columns(2)
            name, phone = a.text_input("Full name", key="au_name"), b.text_input("Phone", key="au_phone")
            email, username = a.text_input("Email", key="au_email"), b.text_input("Username", key="au_user")
            company = a.text_input("Company (vendors)", key="au_company")
            lic = b.text_input("Licence no. (drivers)", key="au_lic")
            op2 = st.selectbox("Operator (drivers)", [None] + list(vl), format_func=lambda i: "-" if i is None else vl[i], key="au_op")
            pw = st.text_input("Starting password", type="password", key="au_pw")
            if st.form_submit_button("Create user", type="primary"):
                if r == "driver" and not op2:
                    st.error("Choose the operator for this driver.")
                else:
                    _, err = auth.create_user(username=username, email=email, password=pw, role=r, full_name=name, phone=phone,
                                              company_name=company, license_no=lic, vendor_id=op2 if r == "driver" else None,
                                              must_change_pw=True)
                    if err:
                        st.error(err)
                    else:
                        ui.flash("User created.")
                        st.rerun()


# ---------------------------------------------------------------- payments
def payments():
    st.header("Payments")
    ui.show_flash()
    if pay.is_configured():
        if st.button("Check online payments"):
            n = pay.sync_all()
            ui.flash(f"{n} new online payment(s) confirmed." if n else "No new online payments.")
            st.rerun()
    rows = db.q("""SELECT p.*, u.username AS customer FROM payments p JOIN bookings b ON b.id=p.booking_id
                   JOIN users u ON u.id=b.customer_id ORDER BY p.id DESC""")
    paid = sum(r["amount"] for r in rows if r["status"] == "paid")
    pending = sum(r["amount"] for r in rows if r["status"] == "pending")
    m = st.columns(3)
    m[0].metric("Paid", money(paid))
    m[1].metric("Pending", money(pending))
    m[2].metric("Payments recorded", len(rows))
    stat_f = st.multiselect("Show", list(ui.PAY_STATUS_LABELS), default=list(ui.PAY_STATUS_LABELS), format_func=ui.PAY_STATUS_LABELS.get)
    rows = [r for r in rows if r["status"] in stat_f]
    if rows:
        mrev, prev = inverse(ui.METHOD_LABELS), inverse(ui.PAY_STATUS_LABELS)
        df = pd.DataFrame([{"ID": r["id"], "Booking": ui.ref(r["booking_id"]), "Customer": r["customer"], "Amount": r["amount"],
                            "Method": ui.METHOD_LABELS[r["method"]], "Status": ui.PAY_STATUS_LABELS[r["status"]],
                            "Reference": r["reference"], "Created": r["created_at"][:16], "Paid at": (r["paid_at"] or "")[:16]} for r in rows])
        edited = st.data_editor(df, hide_index=True, use_container_width=True, key="pay_editor",
                                disabled=["ID", "Booking", "Customer", "Created", "Paid at"],
                                column_config={"Amount": st.column_config.NumberColumn(min_value=0, format="%.0f"),
                                               "Method": st.column_config.SelectboxColumn(options=list(mrev), required=True),
                                               "Status": st.column_config.SelectboxColumn(options=list(prev), required=True)})
        if st.button("Save payment changes", type="primary"):
            changed = 0
            for i, r in enumerate(rows):
                e = edited.iloc[i]
                new = (float(e["Amount"]), mrev[e["Method"]], prev[e["Status"]], str(clean(e["Reference"]) or ""))
                if new != (r["amount"], r["method"], r["status"], r["reference"]):
                    paid_at = db.now_str() if new[2] == "paid" and not r["paid_at"] else r["paid_at"]
                    db.run("UPDATE payments SET amount=?, method=?, status=?, reference=?, paid_at=? WHERE id=?", (*new, paid_at, r["id"]))
                    changed += 1
            ui.flash(f"Saved {changed} payment(s).")
            st.rerun()
    else:
        st.info("No payments to show.")

    bks = [b for b in ui.fetch_bookings(order="b.id DESC") if b["status"] != "cancelled" and b["fare_total"] is not None]
    if bks:
        bl = {b["id"]: f"{b['ref']}: {b['customer']}, due {money(b['due'])}" for b in bks}
        with st.form("add_payment", clear_on_submit=True):
            st.subheader("Record a payment")
            bid = st.selectbox("Booking", list(bl), format_func=bl.get)
            a, b2, c = st.columns(3)
            amt = a.number_input("Amount", min_value=0.0, step=50.0)
            method = b2.selectbox("Method", list(ui.METHOD_LABELS), format_func=ui.METHOD_LABELS.get)
            ref_ = c.text_input("Transaction reference")
            if st.form_submit_button("Save payment", type="primary") and amt > 0:
                db.run("INSERT INTO payments(booking_id,amount,method,status,reference,paid_at) VALUES(?,?,?,?,?,?)",
                       (bid, amt, method, "paid", ref_.strip(), db.now_str()))
                db.run("DELETE FROM payments WHERE booking_id=? AND status='pending'", (bid,))
                ui.flash("Payment recorded.")
                st.rerun()


# ---------------------------------------------------------------- reports
def reports():
    st.header("Reports")
    today = db.now().date()
    c1, c2 = st.columns(2)
    start = c1.date_input("From (pickup date)", value=today - timedelta(days=29))
    end = c2.date_input("To", value=today)
    s, e = start.isoformat(), end.isoformat()
    rng = (s, e)
    where = "date(b.pickup_dt) BETWEEN ? AND ?"
    total = db.q1(f"SELECT COUNT(*) n FROM bookings b WHERE {where}", rng)["n"]
    done = db.q1(f"SELECT COUNT(*) n FROM bookings b WHERE {where} AND b.status='completed'", rng)["n"]
    canc = db.q1(f"SELECT COUNT(*) n FROM bookings b WHERE {where} AND b.status='cancelled'", rng)["n"]
    value = db.q1(f"SELECT COALESCE(SUM(b.fare_total),0) n FROM bookings b WHERE {where} AND b.status!='cancelled'", rng)["n"]
    got = db.q1(f"SELECT COALESCE(SUM(p.amount),0) n FROM payments p JOIN bookings b ON b.id=p.booking_id "
                f"WHERE p.status='paid' AND b.status!='cancelled' AND {where}", rng)["n"]
    m = st.columns(6)
    for col, (label, val) in zip(m, [("Bookings", total), ("Completed", done), ("Cancelled", canc), ("Booked value", money(value)),
                                     ("Collected", money(got)), ("Outstanding", money(max(value - got, 0)))]):
        col.metric(label, val)

    def group(expr, join=""):
        return pd.DataFrame(db.q(
            f"SELECT {expr} AS Name, COUNT(*) AS Bookings, COALESCE(SUM(b.fare_total),0) AS Value FROM bookings b {join} "
            f"WHERE {where} AND b.status!='cancelled' GROUP BY 1 ORDER BY Value DESC", rng))

    def show(title, df, fmt=None):
        st.subheader(title)
        if df.empty:
            st.caption("No data in this period.")
            return
        if fmt:
            df["Name"] = df["Name"].map(fmt)
        st.dataframe(df.style.format({"Value": "\u20b9{:,.0f}"}), hide_index=True, use_container_width=True)

    a, b = st.columns(2)
    with a:
        show("By trip type", group("b.trip_type"), ui.TRIP_LABELS.get)
        show("By city", group("c.name", "JOIN cities c ON c.id=b.city_id"))
        show("By vendor", group("COALESCE(NULLIF(v.company_name,''), v.username)", "JOIN users v ON v.id=b.vendor_id"))
    with b:
        show("By cab type", group("ct.name", "JOIN cab_types ct ON ct.id=b.cab_type_id"))
        st.subheader("By status")
        st_df = pd.DataFrame(db.q(f"SELECT b.status AS Status, COUNT(*) AS Bookings FROM bookings b WHERE {where} GROUP BY 1", rng))
        if not st_df.empty:
            st_df["Status"] = st_df["Status"].map(ui.STATUS_LABELS.get)
            st.dataframe(st_df, hide_index=True, use_container_width=True)
    daily = pd.DataFrame(db.q(
        f"SELECT date(b.pickup_dt) AS Day, COUNT(*) AS Bookings, COALESCE(SUM(b.fare_total),0) AS Value FROM bookings b "
        f"WHERE {where} AND b.status!='cancelled' GROUP BY 1 ORDER BY 1", rng))
    st.subheader("By day")
    if daily.empty:
        st.caption("No data in this period.")
    else:
        st.bar_chart(daily.set_index("Day")["Value"])
        st.dataframe(daily.style.format({"Value": "\u20b9{:,.0f}"}), hide_index=True, use_container_width=True)

    rows = ui.fetch_bookings(where.replace("b.pickup_dt", "b.pickup_dt"), rng, order="b.pickup_dt")
    export = pd.DataFrame([{"Ref": b["ref"], "Pickup": b["pickup_dt"], "Customer": b["customer"], "City": b["city"],
                            "Trip type": ui.TRIP_LABELS[b["trip_type"]], "Route": b["route"], "Cab": b["cab_type"],
                            "Fare": b["fare_total"], "Paid": b["paid"], "Payment": b["pay_state"],
                            "Status": ui.STATUS_LABELS[b["status"]], "Vendor": b["vendor"] or "", "Driver": b["driver"] or "",
                            "Vehicle": b["vehicle_reg"] or ""} for b in rows])
    st.download_button("Download bookings (CSV)", export.to_csv(index=False).encode(), f"gtd_bookings_{s}_{e}.csv", "text/csv")
