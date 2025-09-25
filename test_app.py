import requests

BASE_URL = "http://127.0.0.1:8000"

print("🔹 Probando acceso a / ...")
try:
    res = requests.get(f"{BASE_URL}/")
    print(f"  Status: {res.status_code}")
    print(f"  Content-Type: {res.headers.get('content-type')}")
    print("  Primeros 200 caracteres de la respuesta:")
    print(res.text[:200], "\n")
except Exception as e:
    print("❌ Error conectando al servidor:", e)
    exit()

print("🔹 Probando login ...")
login_data = {"username": "admin", "password": "admin"}  # ⚠️ Ajusta credenciales reales
res = requests.post(f"{BASE_URL}/login", data=login_data)
print(f"  Status: {res.status_code}")
print(f"  JSON: {res.json()}")

if res.ok and "access_token" in res.json():
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    print("\n🔹 Probando acceso al dashboard /dashboard ...")
    res = requests.get(f"{BASE_URL}/dashboard", headers=headers)
    print(f"  Status: {res.status_code}")
    print("  Primeros 200 caracteres de la respuesta:")
    print(res.text[:200], "\n")

    print("🔹 Probando endpoint protegido /protected ...")
    res = requests.get(f"{BASE_URL}/protected", headers=headers)
    print(f"  Status: {res.status_code}")
    try:
        print(f"  JSON: {res.json()}")
    except Exception:
        print("  Respuesta no es JSON:", res.text[:200])

    print("\n🔹 Probando endpoint /status ...")
    res = requests.get(f"{BASE_URL}/status", headers=headers)
    print(f"  Status: {res.status_code}")
    try:
        print(f"  JSON: {res.json()}")
    except Exception:
        print("  Respuesta no es JSON:", res.text[:200])

    print("\n🔹 Probando endpoint /durations ...")
    res = requests.get(f"{BASE_URL}/durations", headers=headers)
    print(f"  Status: {res.status_code}")
    try:
        print(f"  JSON: {res.json()}")
    except Exception:
        print("  Respuesta no es JSON:", res.text[:200])

    print("\n🔹 Probando endpoint /video ...")
    try:
        res = requests.get(f"{BASE_URL}/video", headers=headers, stream=True, timeout=5)
        print(f"  Status: {res.status_code}")
        if res.ok:
            # Verificamos si devuelve bytes (aunque sea parte del stream)
            chunk = next(res.iter_content(1024), None)
            if chunk:
                print(f"  ✅ Recibido chunk de {len(chunk)} bytes (video en marcha)\n")
            else:
                print("  ⚠️ No se recibieron datos del stream\n")
        else:
            print("  ❌ Error accediendo al stream\n")
    except Exception as e:
        print("  ❌ Error probando /video:", e)

else:
    print("❌ Error: no se pudo obtener el token de login")