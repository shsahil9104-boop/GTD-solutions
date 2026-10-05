"""Safe copy of the live database.   python backup.py   (keeps the newest 14 copies in ./backups or $GTD_BACKUP_DIR)"""
import glob
import os
import sqlite3
from datetime import datetime

src = os.environ.get("GTD_DB", "gtd.db")
out_dir = os.environ.get("GTD_BACKUP_DIR", "backups")
os.makedirs(out_dir, exist_ok=True)
dest = os.path.join(out_dir, f"gtd_{datetime.now():%Y%m%d_%H%M}.db")
a, b = sqlite3.connect(src), sqlite3.connect(dest)
a.backup(b)          # consistent even while the app is running
a.close(); b.close()
for old in sorted(glob.glob(os.path.join(out_dir, "gtd_*.db")))[:-14]:
    os.remove(old)
print("Backup saved:", dest)
