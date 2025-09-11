from config import MAX_CAPACITY

def check_capacity(current_inside: int) -> str | None:
    """Devuelve un mensaje si se supera el aforo"""
    if current_inside > MAX_CAPACITY:
        return f"⚠️ Aforo superado: {current_inside}/{MAX_CAPACITY}"
    return None