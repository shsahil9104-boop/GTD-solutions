"""Adds demo logins for testing:  python seed_demo.py   (password for all: demo12345)"""
import auth
import db

db.init()
PW = "demo12345"


def make(username, role, **kw):
    if db.q1("SELECT id FROM users WHERE username=?", (username,)):
        return db.q1("SELECT id FROM users WHERE username=?", (username,))["id"]
    uid, err = auth.create_user(username=username, email=f"{username}@example.com", password=PW, role=role, **kw)
    assert not err, err
    return uid


make("customer1", "customer", full_name="Demo Customer", phone="9876500001")
vendor = make("vendor1", "vendor", full_name="Demo Vendor", phone="9876500002", company_name="Demo Cabs")
make("driver1", "driver", full_name="Demo Driver", phone="9876500003", license_no="GJ0120200001", vendor_id=vendor)
db.run("UPDATE users SET phone_verified=1 WHERE username IN ('customer1','vendor1','driver1')")
sedan = db.q1("SELECT id FROM cab_types WHERE name='Sedan'")["id"]
if not db.q1("SELECT id FROM vehicles WHERE reg_no='GJ01AB1234'"):
    db.run("INSERT INTO vehicles(vendor_id,cab_type_id,name,reg_no,seats) VALUES(?,?,?,?,?)", (vendor, sedan, "Swift Dzire", "GJ01AB1234", 4))
print("Demo accounts ready: customer1, vendor1, driver1 (password demo12345)")
