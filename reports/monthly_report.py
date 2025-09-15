import sqlite3
import csv
from datetime import datetime
from config import DB_PATH

def generate_monthly_report(filepath="reports/monthly_report.csv"):
    today = datetime.now()
    start_month = today.replace(day=1).date()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT person_id, action, timestamp FROM events WHERE DATE(timestamp) >= ?", (start_month.isoformat(),))
    rows = cur.fetchall()
    conn.close()

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Persona", "Acción", "Timestamp"])
        writer.writerows(rows)

    return filepath 