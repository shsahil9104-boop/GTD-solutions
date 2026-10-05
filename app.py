"""GTD Travel Agency - run with:  streamlit run app.py"""
import streamlit as st

import db
import theme
import ui
import p_admin
import p_customer
import p_ops
import p_public

st.set_page_config(page_title="GTD Travel", page_icon="\U0001F696", layout="wide")
theme.inject()


@st.cache_resource
def _init():
    db.init()
    return True


_init()

PAGES = {
    None: {"Log in": p_public.login_page, "Sign up": p_public.signup_page, "Forgot password": p_public.forgot_page,
           "About us": p_public.about_page},
    "customer": {"Book a cab": p_customer.book, "My bookings": p_customer.my_bookings, "Rates": p_public.rates,
                 "About us": p_public.about_page, "My account": None},
    "vendor": {"Bookings": p_ops.vendor_bookings, "Drivers": p_ops.vendor_drivers, "Vehicles": p_ops.vendor_vehicles,
               "About us": p_public.about_page, "My account": None},
    "driver": {"My trips": p_ops.driver_trips, "About us": p_public.about_page, "My account": None},
    "admin": {"Dashboard": p_admin.dashboard, "Bookings": p_admin.bookings, "Rate cards": p_admin.rate_cards,
              "Locations": p_admin.locations, "Cab types": p_admin.cab_types_page, "People": p_admin.people,
              "Payments": p_admin.payments, "Reports": p_admin.reports, "About us": p_public.about_page,
              "My account": None},
}

ICONS = {"Rates": "\U0001F4B0", "Check fare": "\U0001F9EE", "Log in": "\U0001F511", "Sign up": "✨",
         "Forgot password": "\U0001F6DF", "Book a cab": "\U0001F696", "My bookings": "\U0001F4CB", "My account": "\U0001F464",
         "Bookings": "\U0001F4CB", "Drivers": "\U0001F9D1‍✈️", "Vehicles": "\U0001F690", "My trips": "\U0001F9ED",
         "Dashboard": "\U0001F4CA", "Rate cards": "\U0001F3F7️", "Locations": "\U0001F4CD", "Cab types": "\U0001F699",
         "People": "\U0001F465", "Payments": "\U0001F4B3", "Reports": "\U0001F4C8", "About us": "ℹ️"}

ss = st.session_state

# Re-read the signed-in user every run, so switched-off or changed accounts take effect straight away.
if ss.get("user"):
    fresh = db.q1("SELECT * FROM users WHERE id=?", (ss["user"]["id"],))
    if not fresh or not fresh["active"] or (fresh["role"] in ("vendor", "driver") and not fresh["approved"]):
        ss.pop("user", None)
        ss.pop("nav", None)
    else:
        ss["user"] = fresh

user = ss.get("user")
role = user["role"] if user else None

# Phone must be verified by OTP before anyone (except admins) can use the app.
if user and role != "admin" and not user["phone_verified"]:
    with st.sidebar:
        theme.sidebar_brand(user)
        if st.button("Log out", use_container_width=True):
            ss.pop("user", None)
            ss.pop("nav", None)
            st.rerun()
    p_public.verify_phone_page(user)
    st.stop()

pages = PAGES[role]
names = list(pages)

if "_goto" in ss:
    target = ss.pop("_goto")
    if target in names:
        ss["nav"] = target
if ss.get("nav") not in names:
    ss["nav"] = names[0]

with st.sidebar:
    theme.sidebar_brand(user)
    choice = st.radio("Menu", names, key="nav", label_visibility="collapsed",
                      format_func=lambda n: f"{ICONS.get(n, '')}  {n}")
    if user and st.button("Log out", use_container_width=True):
        ss.pop("user", None)
        ss.pop("nav", None)
        st.rerun()

if user and user["must_change_pw"] and choice != "My account" and role != "admin":
    st.warning("You are using a starter password. Open **My account** to change it.")

if choice == "My account":
    ui.account_page(user)
else:
    pages[choice]()
