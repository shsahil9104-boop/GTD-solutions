"""Pages for visitors: rates, about us, login, sign-up, forgot password."""
import pandas as pd
import streamlit as st

import auth
import db
import notify
import sms
import theme
import ui


def home_for(role):
    return {"customer": "Book a cab", "vendor": "Bookings", "driver": "My trips", "admin": "Dashboard"}[role]


def _prefill(city, trip, pickup, drop, cab):
    s = st.session_state
    s["bk_city"], s["bk_type"], s["bk_cab"] = city, trip, cab
    s[f"bk_pickup_{city}"], s[f"bk_drop_{city}"] = pickup, drop
    s["bk_journey"] = "one_way"
    ui.goto("Book a cab")


def rates():
    theme.hero("Pick your route. See the fare at once.",
               "Local, outstation and airport cabs with area-wise rates. Choose pickup, drop and cab type and the fare shows before you book.",
               ["Airport transfers", "Local per-km", "Outstation", "Night-time cover"])
    rows = db.q("""SELECT r.*, c.name AS city, pa.name AS pickup, da.name AS drop_, ct.name AS cab, ct.sort_order
        FROM rate_cards r JOIN cities c ON c.id=r.city_id JOIN cab_types ct ON ct.id=r.cab_type_id
        JOIN areas pa ON pa.id=r.pickup_area_id AND pa.is_airport=1 JOIN areas da ON da.id=r.drop_area_id
        WHERE r.active=1 AND r.trip_type='airport' AND r.journey='one_way' AND r.fixed_fare IS NOT NULL""")
    st.subheader("Airport fares")
    if rows:
        df = pd.DataFrame(rows)
        order = list(df.sort_values("sort_order")["cab"].unique())
        pivot = df.pivot_table(index=["city", "pickup", "drop_"], columns="cab", values="fixed_fare", aggfunc="min")[order]
        pivot = pivot.sort_values(order[0]).reset_index()
        pivot.columns = ["City", "Pickup area", "Drop area"] + order
        st.dataframe(pivot.style.format({c: "\u20b9{:,.0f}" for c in order}, na_rep="-"), hide_index=True, use_container_width=True)
        st.caption("Same fare in both directions.")
        with st.expander("Book one of these fares"):
            by_route = {(r["city_id"], r["pickup_area_id"], r["drop_area_id"]): f"{r['pickup']} to {r['drop_']}" for r in rows}
            route = st.selectbox("Route", list(by_route), format_func=by_route.get)
            cabs = {r["cab_type_id"]: f"{r['cab']}: \u20b9{r['fixed_fare']:,.0f}" for r in rows
                    if (r["city_id"], r["pickup_area_id"], r["drop_area_id"]) == route}
            cab = st.selectbox("Cab", list(cabs), format_func=cabs.get)
            st.button("Check and book", type="primary", on_click=_prefill, args=(route[0], "airport", route[1], route[2], cab))
    else:
        st.info("No airport rates yet. Add rate cards in the admin area.")
    local = db.q("""SELECT c.name AS City, ct.name AS Cab, r.per_km, r.min_km, r.night_surcharge_percent
        FROM rate_cards r JOIN cities c ON c.id=r.city_id JOIN cab_types ct ON ct.id=r.cab_type_id
        WHERE r.active=1 AND r.trip_type='local' AND r.pickup_area_id IS NULL AND r.per_km>0 ORDER BY c.name, ct.sort_order""")
    if local:
        st.subheader("Local rates")
        df = pd.DataFrame(local)
        df["Per km"] = df["per_km"].map(lambda x: f"\u20b9{x:g}")
        df["Minimum km"] = df["min_km"].map(lambda x: f"{x:g}" if x else "n/a")
        df["Night surcharge"] = df["night_surcharge_percent"].map(lambda x: f"{x:g}%" if x else "none")
        st.dataframe(df[["City", "Cab", "Per km", "Minimum km", "Night surcharge"]], hide_index=True, use_container_width=True)


# ---------------------------------------------------------------- about us
STATS_SQL = """SELECT
  (SELECT COUNT(*) FROM cities WHERE active=1) AS cities,
  (SELECT COUNT(*) FROM areas WHERE active=1) AS areas,
  (SELECT COUNT(*) FROM cab_types WHERE active=1) AS cabs,
  (SELECT COUNT(*) FROM users WHERE role='driver' AND active=1) AS drivers,
  (SELECT COUNT(*) FROM users WHERE role='vendor' AND approved=1 AND active=1) AS partners,
  (SELECT COUNT(*) FROM bookings WHERE status='completed') AS trips,
  (SELECT COUNT(*) FROM bookings WHERE status!='cancelled') AS requests"""


def _coverage():
    return db.q("""SELECT c.name AS city, s.name AS state, COUNT(DISTINCT a.id) AS areas,
        COALESCE(SUM(a.is_airport),0) AS airports
        FROM cities c JOIN states s ON s.id=c.state_id
        LEFT JOIN areas a ON a.city_id=c.id AND a.active=1
        WHERE c.active=1 GROUP BY c.id ORDER BY c.name""")


def _about_cta():
    """Bottom call to action. Visitors get the sign-up, signed-in users their own home page."""
    st.subheader("Ready when you are")
    role = (st.session_state.get("user") or {}).get("role")
    st.write("Fares are shown before you book and locked in once you send the request. "
             "You only ever pay what you saw on screen.")
    b1, b2 = st.columns(2)
    if role is None:
        if b1.button("Create an account", type="primary", use_container_width=True):
            ui.goto("Sign up")
            st.rerun()
        if b2.button("Log in", use_container_width=True):
            ui.goto("Log in")
            st.rerun()
    else:
        if b1.button("Go to my page", type="primary", use_container_width=True):
            ui.goto(home_for(role))
            st.rerun()
        if b2.button("Log out", use_container_width=True):
            st.session_state.pop("user", None)
            st.session_state.pop("nav", None)
            st.rerun()
    st.caption("Questions or a fleet to join? Write to "
               f"{notify.ADMIN_EMAIL} or call us and we will call back.")


def about_page():
    """Public 'About us' screen. Open to every role, so every number is read live from the database."""
    ui.show_flash()
    theme.hero("About GTD Travel",
               "One rule runs this business: the fare you see is the fare you pay. Rates are public, "
               "operators are verified and every trip stays traceable from booking to payment.",
               ["Public fares", "Verified operators", "Tracked trips"])

    s = db.q1(STATS_SQL)
    m = st.columns(4)
    m[0].metric("Cities served", s["cities"])
    m[1].metric("Areas covered", s["areas"])
    m[2].metric("Cab types on offer", s["cabs"])
    m[3].metric("Trips completed", s["trips"])

    st.subheader("Who we are")
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("""
GTD Travel is a taxi aggregator built around the two things riders complain about most: fares that
change after the trip, and nobody to call. We publish every rate card in the open, calculate the
fare the moment you pick a route, and hold that figure until the job is done.

We do not own the fleet. Taxi operators and drivers join on their own, keep their own vehicles, and
are allocated the trips that suit them. Our job is the part in between: honest pricing, verified
accounts, and a booking record that nobody has to guess about.
""")
    with right:
        st.markdown("**At a glance**")
        st.markdown(f"""
- **\u20b9{s['requests']:,}** trips accepted, **{s['trips']:,}** completed
- **{s['drivers']:,}** drivers and **{s['partners']:,}** operator partners on the platform
- **{s['areas']:,}** areas across **{s['cities']:,}** cities, airport transfers included
- Local, outstation and airport trips, one-way or round trip
""")

    st.subheader("How a trip works")
    steps = [("\U0001F4DD", "1. Pick your route", "Choose city, pickup, drop and cab type. The fare appears straight away, "
              "itemised as base fare, distance, night surcharge and tolls, so nothing is hidden."),
             ("\U0001F695", "2. We allocate", "Your request goes to our operations desk and the partner fleet best placed "
              "for the job. A driver and vehicle are assigned against your booking."),
             ("\U0001F4CB", "3. Track and settle", "Follow the trip from confirmed to completed, then pay by cash, UPI, card "
              "or bank transfer. Every payment is recorded against your booking reference.")]
    for icon, title, body in steps:
        col = st.columns([1, 8])[1]
        col.markdown(f"{icon} **{title}**")
        col.write(body)

    st.subheader("Who you will ride with")
    cabs = db.q("SELECT * FROM cab_types WHERE active=1 ORDER BY sort_order, name")
    for i in range(0, len(cabs), 2):
        pair = st.columns(2)
        for col, cab in zip(pair, cabs[i:i + 2]):
            with col:
                st.markdown(f"**\U0001F696 {cab['name']}** \u2014 {cab['seats']} seats")
                st.caption(cab["description"] or "Clean, air-conditioned and serviced between trips.")
    st.caption("Every driver on GTD verifies their mobile number with an OTP before they can take a trip, "
               "and every vehicle is registered against an approved operator.")

    st.subheader("Where we run")
    rows = _coverage()
    if rows:
        st.dataframe(pd.DataFrame([{"City": r["city"], "State": r["state"], "Areas covered": r["areas"],
                                    "Airport transfers": "yes" if r["airports"] else "no"} for r in rows]),
                     hide_index=True, use_container_width=True)
        st.caption("Areas, rates and cab types are managed in the admin area, so coverage grows with demand.")
    else:
        st.info("Cities are being added. Check back shortly.")

    st.subheader("Why riders book with us")
    points = [("Fare locked at booking", "The fare shown on screen is carried through to the invoice. We do not "
                "recalculate it later unless you change the trip."),
              ("Real operators, not brokers", "Drivers and vehicles belong to registered fleet partners, so you know "
               "who is picking you up and from which car."),
              ("One record per trip", "Booking, driver, vehicle, fare and payment sit on a single reference you can "
               "quote to us or your operator."),
              ("Bookings in your hand", "Create, review and cancel trips yourself instead of phoning a desk and "
               "waiting for a callback.")]
    for i in range(0, len(points), 2):
        for col, (title, body) in zip(st.columns(2), points[i:i + 2]):
            with col:
                st.markdown(f"**{title}**")
                st.write(body)

    with st.expander("Questions we get asked"):
        for q, a in [("Is the fare final when I book?", "Yes. The amount on the fare card is stored with the booking and "
                       "shown on your invoice. Anything extra, such as a toll you ask the driver to pay, is billed to you."),
                      ("How do I become a driver or join a fleet?", "Drivers are added by their taxi operator. Operators apply "
                       "through Sign up on the vendor tab and are approved by our admin team."),
                      ("Can I cancel or change a trip?", "Open My bookings. Cancellations and changes are free while the trip "
                       "is still pending; once a driver is assigned we confirm with the operator first."),
                      ("How do I pay, and is it safe?", "Cash, UPI, card and bank transfer are all recorded against your "
                       "booking. The driver records cash collected at the end of a trip."),
                      ("Do you cover outstation and round trips?", "Yes. Outstation trips are priced per day with driver "
                       "allowance, and round trips are quoted for the return leg as well.")]:
            st.markdown(f"**{q}**")
            st.write(a)

    _about_cta()


def fare_check():
    st.header("Check fare" if not st.session_state.get("user") else "Book a cab")
    ui.show_flash()
    ui.booking_form(st.session_state.get("user"))


def login_page():
    ui.show_flash()
    theme.hero("Your cab, on time.", "Log in or create an account to check fares and book local, outstation and airport cabs.",
               ["Verified accounts", "Instant fares", "Airport transfers"])
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.header("Welcome back")
        st.caption("Choose your account type, then log in with your username or email.")
        roles = ("customer", "vendor", "driver", "admin")
        notes = {"customer": "New here? Use **Sign up** in the menu.",
                 "vendor": "Run a taxi fleet? Use **Sign up** and choose the vendor tab.",
                 "driver": "Driver accounts are created by your taxi operator.",
                 "admin": "Admin accounts are created by an existing admin."}
        for tab, role in zip(st.tabs([auth.ROLE_LABELS[r] for r in roles]), roles):
            with tab, st.form(f"login_{role}"):
                ident = st.text_input("Username or email", key=f"li_{role}")
                pw = st.text_input("Password", type="password", key=f"lp_{role}")
                if st.form_submit_button("Log in", type="primary", use_container_width=True):
                    user, err = auth.login(ident, pw, role)
                    if err:
                        st.error(err)
                    else:
                        st.session_state["user"] = user
                        ui.goto(home_for(role))
                        st.rerun()
                st.caption(notes[role] + " Forgot your password? Use **Forgot password** in the menu.")
    st.divider()
    left, right = st.columns([3, 1])
    with left:
        st.caption("New to GTD? The **About us** page in the menu explains how fares work, who drives and where we run.")
    with right:
        if st.button("About us", use_container_width=True):
            ui.goto("About us")
            st.rerun()


def signup_page():
    st.header("Sign up")
    t1, t2 = st.tabs(["Customer", "Taxi vendor / operator"])
    with t1, st.form("su_customer"):
        name = st.text_input("Full name")
        phone = st.text_input("Phone")
        email = st.text_input("Email")
        username = st.text_input("Username")
        pw = st.text_input("Password", type="password", help="At least 8 characters.")
        pw2 = st.text_input("Repeat password", type="password")
        if st.form_submit_button("Create account", type="primary"):
            if not (name.strip() and phone.strip()):
                st.error("Enter your name and phone.")
            elif pw != pw2:
                st.error("The two passwords don't match.")
            else:
                uid, err = auth.create_user(username=username, email=email, password=pw, role="customer",
                                            full_name=name, phone=phone)
                if err:
                    st.error(err)
                else:
                    st.session_state["user"] = db.q1("SELECT * FROM users WHERE id=?", (uid,))
                    ui.flash("Welcome to GTD. Book your first cab below.")
                    ui.goto("Book a cab")
                    st.rerun()
    with t2, st.form("su_vendor"):
        company = st.text_input("Company / fleet name")
        name = st.text_input("Contact person")
        phone = st.text_input("Phone", key="vphone")
        email = st.text_input("Email", key="vemail")
        username = st.text_input("Username", key="vuser")
        pw = st.text_input("Password", type="password", key="vpw", help="At least 8 characters.")
        pw2 = st.text_input("Repeat password", type="password", key="vpw2")
        if st.form_submit_button("Apply", type="primary"):
            if not (company.strip() and name.strip() and phone.strip()):
                st.error("Enter company, contact person and phone.")
            elif pw != pw2:
                st.error("The two passwords don't match.")
            else:
                _, err = auth.create_user(username=username, email=email, password=pw, role="vendor", full_name=name,
                                          phone=phone, company_name=company, approved=False)
                if err:
                    st.error(err)
                else:
                    st.success("Thanks. We'll approve your fleet account soon, then you can log in on the Vendor tab.")


def forgot_page():
    st.header("Forgot password")
    st.write("Works for customers, vendors, drivers and admins. We email a one-time code that lasts 30 minutes.")
    with st.form("fp1"):
        email = st.text_input("Email on your account")
        if st.form_submit_button("Email me a code"):
            if email.strip():
                auth.request_reset(email)
            st.session_state["fp_sent"] = email.strip()
            st.success("If an account exists for that email, a code is on its way.")
    st.subheader("I have a code")
    with st.form("fp2"):
        email2 = st.text_input("Email", value=st.session_state.get("fp_sent", ""))
        code = st.text_input("Code from the email")
        pw = st.text_input("New password", type="password", help="At least 8 characters.")
        if st.form_submit_button("Set new password", type="primary"):
            err = auth.complete_reset(email2, code, pw)
            if err:
                st.error(err)
            else:
                ui.flash("Password changed. You can log in now.")
                ui.goto("Log in")
                st.rerun()


def verify_phone_page(user):
    """Shown to every signed-in user until their mobile number is verified by OTP."""
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.header("Verify your phone number")
        ui.show_flash()
        st.write(f"We'll text a 6-digit code to **{auth.mask_phone(user['phone'])}**. You must verify it before using GTD.")
        if not sms.is_configured():
            st.info("Text messages aren't set up on this server yet, so the code is printed in the terminal running Streamlit.")
        if st.button("Send code", type="primary", use_container_width=True):
            ok, msg = auth.send_otp(user["id"])
            (st.success if ok else st.error)(msg)
        with st.form("otp_form"):
            code = st.text_input("6-digit code", max_chars=6, placeholder="123456")
            if st.form_submit_button("Verify", type="primary", use_container_width=True):
                ok, msg = auth.verify_otp(user["id"], code)
                if ok:
                    ui.flash("Phone number verified. Welcome to GTD!")
                    ui.goto(home_for(user["role"]))
                    st.rerun()
                else:
                    st.error(msg)
        with st.expander("Wrong number? Change it"):
            with st.form("change_phone_form"):
                new_phone = st.text_input("Correct mobile number")
                if st.form_submit_button("Update number"):
                    err = auth.change_phone(user["id"], new_phone)
                    if err:
                        st.error(err)
                    else:
                        ui.flash("Number updated. Tap Send code to verify it.")
                        st.rerun()
