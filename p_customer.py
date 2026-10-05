import pandas as pd
import streamlit as st

import db
import ui


def book():
    st.header("Book a cab")
    ui.show_flash()
    ui.booking_form(st.session_state["user"])


def my_bookings():
    user = st.session_state["user"]
    st.header("My bookings")
    ui.show_flash()
    rows = ui.fetch_bookings("b.customer_id=?", (user["id"],))
    if not rows:
        st.info("You haven't booked a cab yet.")
        st.button("Check fare and book", on_click=ui.goto, args=("Book a cab",))
        return
    df = pd.DataFrame([{"Ref": b["ref"], "Route": b["route"], "Pickup": b["pickup_dt"][:16], "Cab": b["cab_type"],
                        "Fare": ui.money(b["fare_total"]) if b["fare_total"] is not None else "To be quoted",
                        "Payment": b["pay_state"], "Status": ui.STATUS_LABELS[b["status"]]} for b in rows])
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.subheader("Details")
    for b in rows:
        with st.expander(f"{b['ref']}: {b['route']} ({ui.STATUS_LABELS[b['status']]})"):
            ui.booking_detail(b)
            if b["status"] in ("pending", "confirmed"):
                if st.button("Cancel this booking", key=f"cx{b['id']}"):
                    db.run("UPDATE bookings SET status='cancelled' WHERE id=?", (b["id"],))
                    ui.flash(f"Booking {b['ref']} cancelled.")
                    st.rerun()
