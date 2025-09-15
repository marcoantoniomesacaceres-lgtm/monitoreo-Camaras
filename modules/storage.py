import sqlite3
from datetime import datetime
from config import DB_PATH


def ensure_schema():
    """
    Garantiza que la tabla 'events' tenga la columna person_id,
    incluso si la base ya existía de antes sin esa columna.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE events ADD COLUMN person_id INTEGER")
    except sqlite3.OperationalError:
        # La columna ya existe o la tabla aún no está creada → no pasa nada
        pass
    conn.commit()
    conn.close()


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
    cur.execute("""
    CREATE TABLE IF NOT EXISTS active_sessions (
        person_id INTEGER PRIMARY KEY,
        entry_time TEXT
    )
    """)
    conn.commit()
    conn.close()

    # 🔹 Garantizar que person_id exista
    ensure_schema()


def save_event(action: str, person_id: int = None):
    """
    Guarda evento en la tabla 'events'.
    Maneja automáticamente sesiones activas para evitar duplicados.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().isoformat()

    if action == "entered":
        # Solo registrar entrada si no existe sesión activa
        cur.execute("SELECT person_id FROM active_sessions WHERE person_id = ?", (person_id,))
        if cur.fetchone() is None:
            cur.execute("INSERT INTO active_sessions (person_id, entry_time) VALUES (?, ?)", (person_id, now))
            cur.execute("INSERT INTO events (person_id, action, timestamp) VALUES (?, ?, ?)", (person_id, action, now))

    elif action == "exited":
        # Solo registrar salida si hay sesión activa
        cur.execute("SELECT entry_time FROM active_sessions WHERE person_id = ?", (person_id,))
        row = cur.fetchone()
        if row:
            cur.execute("DELETE FROM active_sessions WHERE person_id = ?", (person_id,))
            cur.execute("INSERT INTO events (person_id, action, timestamp) VALUES (?, ?, ?)", (person_id, action, now))

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

    # También traer sesiones activas
    cur.execute("SELECT person_id, entry_time FROM active_sessions")
    active_sessions = cur.fetchall()
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

    # Agregar sesiones activas (en curso)
    now = datetime.now()
    for person_id, entry_time in active_sessions:
        entry_time = datetime.fromisoformat(entry_time)
        duration = (now - entry_time).total_seconds()
        durations[person_id] = durations.get(person_id, 0) + duration

    return durations