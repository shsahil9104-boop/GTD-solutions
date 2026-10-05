"""
Adds a Rs 100 base fare to GTD.   Run inside the gtd_streamlit folder:   python add_base_fare.py

 - existing database : sets base_fare = 100 on every per-km / per-hour rate card
 - new databases     : changes the starter local rates in db.py so they also include the base fare
Safe to run twice. Airport (fixed-fare) routes are left alone because those prices are all-inclusive;
set APPLY_TO_FIXED = True to add the base fare on top of them as well (fare.py already shows it as a line).
"""
import os
import sqlite3

BASE_FARE = 100
APPLY_TO_FIXED = False

# 1) starter data for fresh databases
src = open("db.py", encoding="utf-8").read()
old = '''"INSERT INTO rate_cards(city_id,trip_type,journey,cab_type_id,per_km,min_km,night_surcharge_percent)"
            " VALUES(?,?,?,?,?,0,10)"'''
new = f'''"INSERT INTO rate_cards(city_id,trip_type,journey,cab_type_id,base_fare,per_km,min_km,night_surcharge_percent)"
            " VALUES(?,?,?,?,{BASE_FARE},?,0,10)"'''
if old in src:
    open("db.py", "w", encoding="utf-8").write(src.replace(old, new, 1))
    print("db.py: new databases will start with the base fare.")
else:
    print("db.py: already changed (or edited by hand), skipped.")

# 2) existing database
path = os.environ.get("GTD_DB", "gtd.db")
if os.path.exists(path):
    c = sqlite3.connect(path)
    n = c.execute(f"UPDATE rate_cards SET base_fare=? {'' if APPLY_TO_FIXED else 'WHERE fixed_fare IS NULL'}", (BASE_FARE,)).rowcount
    c.commit()
    c.close()
    print(f"{path}: base fare Rs {BASE_FARE} set on {n} rate card(s).")
else:
    print(f"No {path} yet; it will be created with the base fare on first run.")
