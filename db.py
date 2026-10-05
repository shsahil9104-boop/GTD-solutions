"""SQLite storage + first-run seed data. No Streamlit imports, so it can be tested on its own."""
import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

DB_PATH = os.environ.get("GTD_DB", "gtd.db")
TZ = ZoneInfo("Asia/Kolkata")


def now():
    """Current local time (IST) as a naive datetime."""
    return datetime.now(TZ).replace(tzinfo=None)


def now_str():
    return now().strftime("%Y-%m-%d %H:%M:%S")


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def q(sql, params=()):
    with _conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def q1(sql, params=()):
    rows = q(sql, params)
    return rows[0] if rows else None


def run(sql, params=()):
    c = _conn()
    try:
        with c:
            cur = c.execute(sql, params)
            return cur.lastrowid
    finally:
        c.close()


def run_many(statements):
    """statements: list of (sql, params). All-or-nothing."""
    c = _conn()
    try:
        with c:
            for sql, params in statements:
                c.execute(sql, params)
    finally:
        c.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL COLLATE NOCASE,
  email TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL,
  full_name TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL CHECK(role IN ('admin','vendor','driver','customer')),
  company_name TEXT NOT NULL DEFAULT '', license_no TEXT NOT NULL DEFAULT '',
  vendor_id INTEGER REFERENCES users(id),
  approved INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1,
  must_change_pw INTEGER NOT NULL DEFAULT 0,
  phone_verified INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS states(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS cities(
  id INTEGER PRIMARY KEY AUTOINCREMENT, state_id INTEGER NOT NULL REFERENCES states(id),
  name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, UNIQUE(state_id, name));
CREATE TABLE IF NOT EXISTS areas(
  id INTEGER PRIMARY KEY AUTOINCREMENT, city_id INTEGER NOT NULL REFERENCES cities(id),
  name TEXT NOT NULL, is_airport INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
  UNIQUE(city_id, name));
CREATE TABLE IF NOT EXISTS cab_types(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, seats INTEGER NOT NULL DEFAULT 4,
  description TEXT NOT NULL DEFAULT '', sort_order INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS vehicles(
  id INTEGER PRIMARY KEY AUTOINCREMENT, vendor_id INTEGER REFERENCES users(id),
  cab_type_id INTEGER NOT NULL REFERENCES cab_types(id), name TEXT NOT NULL,
  reg_no TEXT UNIQUE NOT NULL, seats INTEGER NOT NULL DEFAULT 4, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS rate_cards(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  city_id INTEGER NOT NULL REFERENCES cities(id),
  trip_type TEXT NOT NULL CHECK(trip_type IN ('local','outstation','airport')),
  journey TEXT NOT NULL DEFAULT 'one_way' CHECK(journey IN ('one_way','round_trip')),
  cab_type_id INTEGER NOT NULL REFERENCES cab_types(id),
  pickup_area_id INTEGER REFERENCES areas(id), drop_area_id INTEGER REFERENCES areas(id),
  bidirectional INTEGER NOT NULL DEFAULT 1,
  fixed_fare REAL, base_fare REAL NOT NULL DEFAULT 0, per_km REAL NOT NULL DEFAULT 0,
  per_hour REAL NOT NULL DEFAULT 0, min_km REAL NOT NULL DEFAULT 0, min_hours REAL NOT NULL DEFAULT 0,
  driver_allowance REAL NOT NULL DEFAULT 0, toll_parking_permit REAL NOT NULL DEFAULT 0,
  night_surcharge_percent REAL NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS bookings(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES users(id),
  city_id INTEGER NOT NULL REFERENCES cities(id),
  trip_type TEXT NOT NULL, journey TEXT NOT NULL DEFAULT 'one_way',
  pickup_area_id INTEGER NOT NULL REFERENCES areas(id), drop_area_id INTEGER REFERENCES areas(id),
  pickup_address TEXT NOT NULL DEFAULT '', drop_address TEXT NOT NULL DEFAULT '',
  cab_type_id INTEGER NOT NULL REFERENCES cab_types(id),
  pickup_dt TEXT NOT NULL, return_date TEXT, passengers INTEGER NOT NULL DEFAULT 1,
  distance_km REAL, hours REAL, notes TEXT NOT NULL DEFAULT '',
  rate_card_id INTEGER REFERENCES rate_cards(id), fare_total REAL, fare_lines TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'pending',
  vendor_id INTEGER REFERENCES users(id), driver_id INTEGER REFERENCES users(id),
  vehicle_id INTEGER REFERENCES vehicles(id), admin_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  amount REAL NOT NULL, method TEXT NOT NULL DEFAULT 'cash', status TEXT NOT NULL DEFAULT 'pending',
  reference TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, paid_at TEXT);
CREATE TABLE IF NOT EXISTS otp_codes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id), phone TEXT NOT NULL,
  code_hash TEXT NOT NULL, expires_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  used INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reset_tokens(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
  token_hash TEXT NOT NULL, expires_at TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0);
"""

AREAS = ["SG Highway / Prahladnagar", "Satellite / Jodhpur", "CG Road / Ashram Road", "Maninagar / Kankaria",
         "Science City / Sola / Gota", "Bopal / South Bopal", "Naroda / Narol / Vatva", "Gandhinagar"]
# Airport -> area fixed fares for Sedan, SUV/Ertiga, Crysta
AIRPORT_FARES = {
    "SG Highway / Prahladnagar": (450, 600, 800), "Satellite / Jodhpur": (500, 650, 850),
    "CG Road / Ashram Road": (600, 780, 1000), "Maninagar / Kankaria": (750, 950, 1200),
    "Science City / Sola / Gota": (400, 550, 720), "Bopal / South Bopal": (650, 820, 1050),
    "Naroda / Narol / Vatva": (800, 1000, 1280), "Gandhinagar": (900, 1100, 1400),
}


def seed_core():
    """Ahmedabad areas, cab types and the starting rate cards (runs once, on an empty database)."""
    if q1("SELECT id FROM cities LIMIT 1"):
        return
    sid = run("INSERT INTO states(name) VALUES('Gujarat')")
    cid = run("INSERT INTO cities(state_id,name) VALUES(?,?)", (sid, "Ahmedabad"))
    airport = run("INSERT INTO areas(city_id,name,is_airport) VALUES(?,?,1)", (cid, "Airport"))
    area_ids = {n: run("INSERT INTO areas(city_id,name) VALUES(?,?)", (cid, n)) for n in AREAS}
    cabs = {}
    for name, seats, order in (("Sedan", 4, 1), ("SUV/Ertiga", 6, 2), ("Crysta", 7, 3), ("Premium", 4, 4)):
        cabs[name] = run("INSERT INTO cab_types(name,seats,sort_order) VALUES(?,?,?)", (name, seats, order))
    for area, fares in AIRPORT_FARES.items():
        for cab, fare in zip(("Sedan", "SUV/Ertiga", "Crysta"), fares):
            run("INSERT INTO rate_cards(city_id,trip_type,journey,cab_type_id,pickup_area_id,drop_area_id,fixed_fare)"
                " VALUES(?,?,?,?,?,?,?)", (cid, "airport", "one_way", cabs[cab], airport, area_ids[area], fare))
    # Local, city-wide: Sedan Rs 20/km, SUV Rs 25/km, no minimum, 10% night surcharge
    for cab, rate in (("Sedan", 20), ("SUV/Ertiga", 25)):
        run("INSERT INTO rate_cards(city_id,trip_type,journey,cab_type_id,base_fare,per_km,min_km,night_surcharge_percent)"
            " VALUES(?,?,?,?,100,?,0,10)", (cid, "local", "one_way", cabs[cab], rate))


def init():
    c = _conn()
    try:
        with c:
            c.executescript(SCHEMA)
    finally:
        c.close()
    # upgrade databases created before phone verification existed
    if "phone_verified" not in [r["name"] for r in q("PRAGMA table_info(users)")]:
        run("ALTER TABLE users ADD COLUMN phone_verified INTEGER NOT NULL DEFAULT 0")
    seed_core()
    from auth import create_default_admin  # imported late: auth imports db
    create_default_admin()
