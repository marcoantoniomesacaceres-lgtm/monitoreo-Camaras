import sqlite3
from passlib.context import CryptContext

db_path = "data/database.db"
usuario = "admin"
contraseña = "1234"
full_name = "Administrador"
role = "admin"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hash_nuevo = pwd_context.hash(contraseña)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    full_name TEXT,
    hashed_password TEXT,
    role TEXT
)
""")
cursor.execute("INSERT OR REPLACE INTO users (username, full_name, hashed_password, role) VALUES (?, ?, ?, ?)",
               (usuario, full_name, hash_nuevo, role))
conn.commit()
conn.close()
print("Usuario admin creado o actualizado.")
