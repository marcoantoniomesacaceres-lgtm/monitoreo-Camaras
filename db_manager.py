import sqlite3
import os
import sys
from passlib.context import CryptContext

# 📦 Configuración
DB_PATH = os.path.join("data", "SISMONICAMARAS.db")
os.makedirs("data", exist_ok=True)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Usuarios iniciales
initial_users = [
    ("admin", "Administrador del sistema", "admin123", "admin"),
    ("operador", "Operador de cámaras", "operador123", "operator"),
    ("viewer", "Visualizador", "viewer123", "viewer"),
]

def get_connection():
    return sqlite3.connect(DB_PATH)

# ------------------------------
# 🚀 Inicializar tabla de usuarios
# ------------------------------
def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # Crear tabla users si no existe
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        full_name TEXT,
        hashed_password TEXT NOT NULL,
        role TEXT NOT NULL
    )
    """)

    # Insertar usuarios iniciales
    for username, full_name, plain_password, role in initial_users:
        hashed_password = pwd_context.hash(plain_password)
        try:
            cur.execute(
                "INSERT INTO users (username, full_name, hashed_password, role) VALUES (?, ?, ?, ?)",
                (username, full_name, hashed_password, role),
            )
            print(f"✅ Usuario {username} creado")
        except sqlite3.IntegrityError:
            print(f"ℹ️ Usuario {username} ya existe, no se modificó")

    conn.commit()
    conn.close()
    print("🚀 Inicialización completada")

# ------------------------------
# 🛠️ Migración: agregar columna person_id a events
# ------------------------------
def fix_db():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE events ADD COLUMN person_id INTEGER")
        print("✅ Columna 'person_id' agregada con éxito")
    except sqlite3.OperationalError as e:
        print("⚠️ No se pudo agregar la columna (quizá ya existe):", e)
    conn.commit()
    conn.close()

# ------------------------------
# 🎛️ Main dispatcher
# ------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python db_manager.py [init|fix]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        init_db()
    elif command == "fix":
        fix_db()
    else:
        print(f"Comando desconocido: {command}")
        print("Uso: python db_manager.py [init|fix]") 