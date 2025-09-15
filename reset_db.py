import os
from modules import storage
from config import DB_PATH

def reset_db():
    # Si existe el archivo de la base de datos, lo eliminamos
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"✅ Base de datos eliminada: {DB_PATH}")
    else:
        print(f"⚠️ No se encontró la base de datos en: {DB_PATH}")

    # Volvemos a crearla con la estructura correcta
    storage.init_db()
    print("✅ Nueva base de datos creada con la estructura actualizada.")

if __name__ == "__main__":
    reset_db()