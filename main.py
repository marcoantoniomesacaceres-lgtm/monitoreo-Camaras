from fastapi import FastAPI
from modules import storage, alerts, notifications



app = FastAPI()

# Inicializar base de datos
if __name__ == "__main__":
    storage.init_db()
    storage.save_event("inicio")
    print(storage.get_stats())

# Estado en memoria (simplificado)
STATE = {
    "inside": 0,
    "entered": 0,
    "exited": 0,
}


@app.get("/")
async def root():
    return {"message": "SISMONICAMARAS API running 🚀"}


@app.get("/status")
async def get_status():
    """Devuelve estado actual"""
    return STATE


@app.post("/event/{action}")
async def register_event(action: str):
    """
    Registra un evento manual (ejemplo: 'entered', 'exited')
    Más adelante aquí irá la integración con detección real.
    """
    if action not in ["entered", "exited"]:
        return {"error": "Acción no válida"}

    if action == "entered":
        STATE["entered"] += 1
        STATE["inside"] += 1
    else:
        STATE["exited"] += 1
        STATE["inside"] = max(0, STATE["inside"] - 1)

    storage.save_event(action)

    # Checar alertas
    alert_msg = alerts.check_capacity(STATE["inside"])
    if alert_msg:
        notifications.send_email("Alerta de aforo", alert_msg)

    return {"status": "ok", "state": STATE}


@app.get("/stats")
async def get_stats():
    """Estadísticas históricas desde SQLite"""
    return storage.get_stats()