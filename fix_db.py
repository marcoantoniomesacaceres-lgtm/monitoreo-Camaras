import sqlite3

def fix_db():
    conn = sqlite3.connect("data/SISMONICAMARAS.db")  # ajusta la ruta si tu archivo está en otra carpeta
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE events ADD COLUMN person_id INTEGER")
        print("✅ Columna 'person_id' agregada con éxito")
    except sqlite3.OperationalError as e:
        print("⚠️ No se pudo agregar la columna (quizá ya existe):", e)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    fix_db()
