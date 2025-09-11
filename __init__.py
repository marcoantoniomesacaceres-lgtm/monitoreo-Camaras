from modules import storage

if __name__ == "__main__":
    storage.init_db()
    storage.save_event("inicio")
    print(storage.get_stats())