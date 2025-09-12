import sqlite3
from datetime import datetime
from config import DB_PATH


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id INTEGER,
        action TEXT,
        timestamp TEXT
    )
    """)
    conn.commit()
    conn.close()


def save_event(action: str, person_id: int = None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO events (person_id, action, timestamp) VALUES (?, ?, ?)",
        (person_id, action, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT action, COUNT(*) FROM events GROUP BY action")
    data = cur.fetchall()
    conn.close()
    return dict(data)


def get_person_durations():
    """
    Devuelve el tiempo de permanencia (en segundos) por persona.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT person_id, action, timestamp FROM events ORDER BY timestamp")
    rows = cur.fetchall()
    conn.close()

    durations = {}
    check_in = {}

    for person_id, action, ts in rows:
        if not person_id:
            continue
        ts = datetime.fromisoformat(ts)
        if action == "entered":
            check_in[person_id] = ts
        elif action == "exited" and person_id in check_in:
            duration = (ts - check_in[person_id]).total_seconds()
            durations[person_id] = durations.get(person_id, 0) + duration
            del check_in[person_id]

    return durations