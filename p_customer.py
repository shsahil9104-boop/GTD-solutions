import pandas as pd
import streamlit as st

import db
import pay
import ui


def _pay_section(b):
    """Pay-online controls for one booking (shown inside its expander)."""
    if b["status"] == "cancelled" or b["fare_total"] is None or b["due"] <= 0 or not pay.is_configured():
        return
    st.markdown(f"**Amount due: {ui.money(b['due'])}**")
    if pay.is_test_mode():
        st.caption("Test mode: no real money is charged.")
    url_key = f"payurl{b['id']}"
    if st.button("Pay online", key=f"pay{b['id']}", type="primary"):
        url, msg = pay.start_payment(b)
        if url:
            st.session_state[url_key] = url
        else:
            st.session_state.pop(url_key, None)
            st.warning(msg)
            if "already paid" in msg:
                st.rerun()
    if st.session_state.get(url_key):
        st.link_button("Open payment page", st.session_state[url_key])
        st.caption("The payment page opens in a new tab. When you have paid, come back here and press the button below.")
        if st.button("I've paid, check status", key=f"chk{b['id']}"):
            if pay.sync_customer(st.session_state["user"]["id"], force=True):
                st.session_state.pop(url_key, None)
                ui.flash("Payment received. Thank you!")
                st.rerun()
            else:
                st.info("We haven't received the payment yet. If you just paid, wait a few seconds and try again.")


def book():
    st.header("Book a cab")
    ui.show_flash()
    ui.booking_form(st.session_state["user"])


def my_bookings():
    user = st.session_state["user"]
    st.header("My bookings")
    if pay.is_configured() and pay.sync_customer(user["id"]):
        ui.flash("Payment received. Thank you!")
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
            _pay_section(b)
            if b["status"] in ("pending", "confirmed"):
                if st.button("Cancel this booking", key=f"cx{b['id']}"):
                    db.run("UPDATE bookings SET status='cancelled' WHERE id=?", (b["id"],))
                    ui.flash(f"Booking {b['ref']} cancelled.")
                    st.rerun()
