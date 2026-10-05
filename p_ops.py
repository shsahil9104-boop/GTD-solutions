"""Vendor and driver screens."""
import pandas as pd
import streamlit as st

import auth
import db
import ui


# ---------------------------------------------------------------- vendor
def vendor_bookings():
    user = st.session_state["user"]
    st.header("Bookings given to you")
    ui.show_flash()
    rows = ui.fetch_bookings("b.vendor_id=? AND b.status!='cancelled'", (user["id"],), order="b.pickup_dt")
    if not rows:
        st.info("No bookings have been allocated to you yet. GTD admin assigns trips to operators.")
        return
    drivers = db.q("SELECT id, full_name, username FROM users WHERE role='driver' AND vendor_id=? AND active=1", (user["id"],))
    vehicles = db.q("SELECT id, name, reg_no FROM vehicles WHERE vendor_id=? AND active=1", (user["id"],))
    dlabel = {d["id"]: d["full_name"] or d["username"] for d in drivers}
    vlabel = {v["id"]: f"{v['name']} ({v['reg_no']})" for v in vehicles}
    for b in rows:
        title = f"{b['ref']}: {b['route']}, {b['pickup_dt'][:16]} ({ui.STATUS_LABELS[b['status']]})"
        with st.expander(title, expanded=b["status"] in ("pending", "confirmed")):
            ui.booking_detail(b)
            if b["status"] in ("pending", "confirmed", "assigned"):
                if not drivers or not vehicles:
                    st.warning("Add at least one driver and one vehicle first.")
                    continue
                c1, c2, c3 = st.columns([2, 2, 1])
                d = c1.selectbox("Driver", list(dlabel), format_func=dlabel.get, key=f"vd{b['id']}",
                                 index=list(dlabel).index(b["driver_id"]) if b["driver_id"] in dlabel else 0)
                v = c2.selectbox("Vehicle", list(vlabel), format_func=vlabel.get, key=f"vv{b['id']}",
                                 index=list(vlabel).index(b["vehicle_id"]) if b["vehicle_id"] in vlabel else 0)
                c3.write("")
                if c3.button("Assign", key=f"va{b['id']}", type="primary"):
                    db.run("UPDATE bookings SET driver_id=?, vehicle_id=?, status='assigned' WHERE id=? AND vendor_id=?",
                           (d, v, b["id"], user["id"]))
                    ui.flash(f"{b['ref']}: driver and vehicle assigned.")
                    st.rerun()


def vendor_drivers():
    user = st.session_state["user"]
    st.header("My drivers")
    ui.show_flash()
    rows = db.q("SELECT full_name AS Name, username AS Username, phone AS Phone, license_no AS Licence, active AS Active "
                "FROM users WHERE role='driver' AND vendor_id=?", (user["id"],))
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No drivers yet. Add your first one below.")
    with st.form("add_driver", clear_on_submit=True):
        st.subheader("Add a driver")
        name = st.text_input("Full name")
        c1, c2 = st.columns(2)
        phone, lic = c1.text_input("Phone"), c2.text_input("Driving licence no.")
        email, username = c1.text_input("Email"), c2.text_input("Username")
        pw = st.text_input("Starting password", type="password", help="Share it with the driver. They can reset it later.")
        if st.form_submit_button("Add driver", type="primary"):
            if not (name.strip() and phone.strip() and lic.strip()):
                st.error("Enter name, phone and licence number.")
            else:
                _, err = auth.create_user(username=username, email=email, password=pw, role="driver", full_name=name,
                                          phone=phone, license_no=lic, vendor_id=user["id"], approved=True)
                if err:
                    st.error(err)
                else:
                    ui.flash("Driver added. They can log in on the Driver tab.")
                    st.rerun()


def vendor_vehicles():
    user = st.session_state["user"]
    st.header("My vehicles")
    ui.show_flash()
    rows = db.q("SELECT v.name AS Model, v.reg_no AS Registration, c.name AS 'Cab type', v.seats AS Seats, v.active AS Active "
                "FROM vehicles v JOIN cab_types c ON c.id=v.cab_type_id WHERE v.vendor_id=?", (user["id"],))
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No vehicles yet. Add your first one below.")
    cabs = ui.cab_types()
    clabel = {c["id"]: c["name"] for c in cabs}
    with st.form("add_vehicle", clear_on_submit=True):
        st.subheader("Add a vehicle")
        cab = st.selectbox("Cab type", list(clabel), format_func=clabel.get)
        c1, c2, c3 = st.columns(3)
        name, reg = c1.text_input("Model (e.g. Swift Dzire)"), c2.text_input("Registration no.")
        seats = c3.number_input("Seats", min_value=1, max_value=60, value=4)
        if st.form_submit_button("Add vehicle", type="primary"):
            if not (name.strip() and reg.strip()):
                st.error("Enter the model and registration number.")
            elif db.q1("SELECT id FROM vehicles WHERE reg_no=? COLLATE NOCASE", (reg.strip(),)):
                st.error("This registration number is already listed.")
            else:
                db.run("INSERT INTO vehicles(vendor_id,cab_type_id,name,reg_no,seats) VALUES(?,?,?,?,?)",
                       (user["id"], cab, name.strip(), reg.strip().upper(), int(seats)))
                ui.flash("Vehicle added.")
                st.rerun()


# ---------------------------------------------------------------- driver
def driver_trips():
    user = st.session_state["user"]
    st.header("My trips")
    ui.show_flash()
    rows = ui.fetch_bookings("b.driver_id=? AND b.status!='cancelled'", (user["id"],), order="b.pickup_dt")
    if not rows:
        st.info("No trips assigned to you yet.")
        return
    for b in rows:
        with st.expander(f"{b['ref']}: {b['route']}, {b['pickup_dt'][:16]} ({ui.STATUS_LABELS[b['status']]})",
                         expanded=b["status"] in ("assigned", "ongoing")):
            st.write(f"**Customer:** {b['customer_name'] or b['customer']}, {b['customer_phone']}")
            st.write(f"**Vehicle:** {b['vehicle_reg'] or '-'}   **Fare due:** {ui.money(b['due'])}")
            ui.booking_detail(b)
            c1, c2, c3 = st.columns(3)
            if b["status"] == "assigned" and c1.button("Start trip", key=f"s{b['id']}", type="primary"):
                db.run("UPDATE bookings SET status='ongoing' WHERE id=? AND driver_id=?", (b["id"], user["id"]))
                ui.flash(f"{b['ref']}: trip started.")
                st.rerun()
            if b["status"] == "ongoing" and c2.button("Complete trip", key=f"c{b['id']}", type="primary"):
                db.run("UPDATE bookings SET status='completed' WHERE id=? AND driver_id=?", (b["id"], user["id"]))
                ui.flash(f"{b['ref']}: trip completed.")
                st.rerun()
            if b["status"] in ("ongoing", "completed") and b["due"] > 0 and c3.button("Cash collected", key=f"m{b['id']}"):
                due = ui.mark_cash_collected(b["id"])
                ui.flash(f"{b['ref']}: {ui.money(due)} cash recorded.")
                st.rerun()
