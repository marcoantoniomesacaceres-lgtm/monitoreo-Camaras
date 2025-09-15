import sqlite3
import csv
from datetime import datetime, timedelta
from config import DB_PATH

def generate_weekly_report(filepath="reports/weekly_report.csv"):
    today = datetime.now().date()
    start_week = today - timedelta(days=today.weekday())  # lunes
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT person_id, action, timestamp FROM events WHERE DATE(timestamp) >= ?", (start_week.isoformat(),))
    rows = cur.fetchall()
    conn.close()

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Persona", "Acción", "Timestamp"])
        writer.writerows(rows)

    return filepath