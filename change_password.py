import sys
from passlib.context import CryptContext
import sqlite3

if len(sys.argv) != 4:
    print("Uso: python change_password.py <usuario> <nueva_contraseña> <ruta_db>")
    sys.exit(1)

usuario = sys.argv[1]
nueva_contra = sys.argv[2]
ruta_db = sys.argv[3]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
hash_nuevo = pwd_context.hash(nueva_contra)

conn = sqlite3.connect(ruta_db)
cursor = conn.cursor()

cursor.execute("UPDATE users SET hashed_password = ? WHERE username = ?", (hash_nuevo, usuario))
if cursor.rowcount == 0:
    print(f"Usuario '{usuario}' no encontrado.")
else:
    print(f"Contraseña actualizada para '{usuario}'.")
conn.commit()
conn.close()
