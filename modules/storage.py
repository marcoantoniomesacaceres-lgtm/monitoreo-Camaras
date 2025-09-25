import sqlite3
import threading
import logging
import os
from datetime import datetime

# -----------------------------
# 📂 Configuración DB
# -----------------------------
logger = logging.getLogger(__name__)
DB_DIR = "data"
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "database.db")

# 🔹 Conexión global + Lock
_conn = None
_db_lock = threading.Lock()

# -----------------------------
# 🔗 Conexión
# -----------------------------
def get_connection():
    """
    Retorna la conexión global si existe,
    si no, crea una nueva conexión.
    """
    global _conn
    if _conn is None:
        try:
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        except Exception as e:
            logger.error(f"❌ Error creando conexión DB: {e}", exc_info=True)
            raise
    return _conn


def close_db():
    """
    Cierra la conexión global si existe.
    """
    global _conn
    if _conn:
        try:
            _conn.close()
            logger.info("ℹ️ Conexión DB cerrada")
        except Exception as e:
            logger.error(f"❌ Error cerrando DB: {e}", exc_info=True)
        finally:
            _conn = None

# -----------------------------
# 🛠️ Inicialización / Schema
# -----------------------------
def ensure_schema():
    """
    Asegura que el esquema mínimo esté correcto.
    """
    with _db_lock:
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE events ADD COLUMN person_id INTEGER")
        except sqlite3.OperationalError:
            # Ya existe la columna o la tabla aún no está creada → ignorar
            pass
        conn.commit()


def init_db():
    """
    Inicializa la base de datos. 
    No bloquea FastAPI en caso de error.
    """
    try:
        with _db_lock:
            conn = get_connection()
            cur = conn.cursor()

            # Tabla de eventos
            cur.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_id INTEGER,
                    action TEXT,
                    timestamp TEXT
                )
            """)

            # Tabla de sesiones activas
            cur.execute("""
                CREATE TABLE IF NOT EXISTS active_sessions (
                    person_id INTEGER PRIMARY KEY,
                    entry_time TEXT
                )
            """)

            conn.commit()

            # Garantizar columnas mínimas
            ensure_schema()

        logger.info("✅ Base de datos lista en %s", DB_PATH)
    except Exception as e:
        logger.error(f"❌ Error inicializando la DB: {e}", exc_info=True)

# -----------------------------
# 📌 Eventos
# -----------------------------
def save_event(action: str, person_id: int = None):
    """
    Guarda evento en la tabla 'events'.
    Maneja sesiones activas para evitar duplicados.
    """
    with _db_lock:
        try:
            conn = get_connection()
            cur = conn.cursor()
            now = datetime.now().isoformat()

            if action == "entered":
                cur.execute("SELECT person_id FROM active_sessions WHERE person_id = ?", (person_id,))
                if cur.fetchone() is None:
                    cur.execute(
                        "INSERT INTO active_sessions (person_id, entry_time) VALUES (?, ?)",
                        (person_id, now)
                    )
                    cur.execute(
                        "INSERT INTO events (person_id, action, timestamp) VALUES (?, ?, ?)",
                        (person_id, action, now)
                    )

            elif action == "exited":
                cur.execute("SELECT entry_time FROM active_sessions WHERE person_id = ?", (person_id,))
                row = cur.fetchone()
                if row:
                    cur.execute("DELETE FROM active_sessions WHERE person_id = ?", (person_id,))
                    cur.execute(
                        "INSERT INTO events (person_id, action, timestamp) VALUES (?, ?, ?)",
                        (person_id, action, now)
                    )

            conn.commit()
            logger.info("📌 Evento guardado: %s - %s", action, person_id)

        except Exception as e:
            logger.error(f"❌ Error guardando evento: {e}", exc_info=True)

# -----------------------------
# 📊 Consultas
# -----------------------------
def get_stats():
    """
    Retorna estadísticas de eventos.
    """
    with _db_lock:
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT action, COUNT(*) FROM events GROUP BY action")
            data = cur.fetchall()
            return dict(data)
        except Exception as e:
            logger.error(f"❌ Error obteniendo estadísticas: {e}", exc_info=True)
            return {}


def get_person_durations():
    """
    Devuelve el tiempo de permanencia (en segundos) por persona.
    """
    with _db_lock:
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT person_id, action, timestamp FROM events ORDER BY timestamp")
            rows = cur.fetchall()

            cur.execute("SELECT person_id, entry_time FROM active_sessions")
            active_sessions = cur.fetchall()
        except Exception as e:
            logger.error(f"❌ Error obteniendo duraciones: {e}", exc_info=True)
            return {}

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

    # Sesiones activas en curso
    now = datetime.now()
    for person_id, entry_time in active_sessions:
        entry_time = datetime.fromisoformat(entry_time)
        duration = (now - entry_time).total_seconds()
        durations[person_id] = durations.get(person_id, 0) + duration

    return durations