# GTD Travel Agency (Streamlit)

Same site as the Django version: roles, area-wise rate cards, automatic fares, dashboards and reports.

## Run it
```
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python seed_demo.py          # optional: demo logins customer1 / vendor1 / driver1 (password demo12345)
streamlit run app.py
```
First start creates `gtd.db` (SQLite) with Ahmedabad areas, cab types and your starting rates.
**Admin login:** username `admin`, password `admin123`. You are asked to change it. To pick your own,
set `GTD_ADMIN_USER` and `GTD_ADMIN_PASSWORD` before the first start.

## Roles
| Role | Account | Can do |
|---|---|---|
| Customer | Sign up | Live fare, book, cancel, see own bookings |
| Vendor | Applies, admin approves (People page) | Add drivers and vehicles, assign them to bookings given to them |
| Driver | Created by their vendor | Start / complete trips, record cash collected |
| Admin | Created by an admin | Everything below |

Log in with username or email on the matching tab. Menus and pages are limited by role.

## Admin menu
Dashboard, Bookings (edit fare / vendor / driver / status in the grid, recalculate fares), Rate cards (edit in the grid,
add, delete, change all shown rates by a %), Locations (State > City > Area), Cab types, People (approve, switch off,
reset passwords, change roles, add users), Payments, Reports (with CSV download).

## Rates
A rate card = city + trip type (Local / Outstation / Airport) + journey (one-way / round trip) + cab type + optional
pickup/drop area, with fixed fare, base fare, per-km, per-hour, minimum km/hours, driver allowance per day,
toll/parking/permit and night surcharge %. Best match wins: exact route, reversed route, pickup area, city-wide.
Night = pickup from 22:00 to 05:59 (`NIGHT_START_HOUR` in `fare.py`).

## Phone verification (OTP)
Customers, vendors and drivers must verify their mobile number with a 6-digit SMS code before they can use the app
(admins are exempt). Codes last 5 minutes, allow 5 wrong tries, can be resent every 30 seconds, and are limited to 5 per hour.
Existing accounts are asked to verify at their next login. Users can change their number from the verify screen or My account.

SMS needs a provider. Twilio is built in; set `GTD_TWILIO_SID`, `GTD_TWILIO_TOKEN` and `GTD_TWILIO_FROM` (a Twilio number).
Without them the code is **printed in the terminal** instead (fine for testing, no real texts are sent).
For Indian operators such as MSG91 or Fast2SMS, replace the body of `send_sms` in `sms.py`.

## Login required
Every page needs a login, except **About us**, which is open to visitors as well as signed-in users of any role.
Visitors see Log in, Sign up, Forgot password and About us.

## Trip requests by email
Each new booking emails **shsahil9894@gmail.com** (change with `GTD_ADMIN_EMAIL`) with the customer, route, cab and fare.
Real sending needs SMTP settings; for Gmail create an App Password and set:
```
GTD_SMTP_HOST=smtp.gmail.com   GTD_SMTP_PORT=587
GTD_SMTP_USER=your@gmail.com   GTD_SMTP_PASSWORD=<app password>   GTD_SMTP_FROM="GTD Travel <your@gmail.com>"
```
Without SMTP the email is only printed in the terminal.

## Google Maps
`gmaps.py` is a ready script (not wired into the booking form). See its header for key setup and use `gmaps.trip_map()` on any page.

## Forgot password
Emails a one-time code (30 minutes). Set `GTD_SMTP_HOST`, `GTD_SMTP_PORT`, `GTD_SMTP_USER`, `GTD_SMTP_PASSWORD`,
`GTD_SMTP_FROM` to send real email. Without them the email is printed in the terminal running Streamlit.

## Deploying
See **DEPLOY.md** for step-by-step setup on Render or your own Linux server, plus daily backups (`python backup.py`).
Do not use Streamlit Community Cloud: it erases the database file on restart.

## Base fare
Local (per-km) rate cards start with a Rs 100 base fare. Airport routes are fixed all-inclusive fares and have none.
If you already have a `gtd.db` from an older version, run `python add_base_fare.py` once to apply it. Rates can be changed any time in Admin > Rate cards.
