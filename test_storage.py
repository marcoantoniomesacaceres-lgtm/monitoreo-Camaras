from modules import storage

def main():
    print("🔹 Inicializando base de datos...")
    storage.init_db()

    print("\n🔹 Guardando eventos de prueba...")
    storage.save_event("entered", 1)
    storage.save_event("entered", 2)
    storage.save_event("exited", 1)

    print("\n🔹 Estadísticas de eventos:")
    stats = storage.get_stats()
    print(stats)

    print("\n🔹 Duraciones por persona:")
    durations = storage.get_person_durations()
    print(durations)

    print("\n🔹 Cerrando conexión...")
    storage.close_db()

if __name__ == "__main__":
    main()
