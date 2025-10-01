from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request, Cookie
from fastapi.security import OAuth2PasswordBearer

# 📦 Importar conexión a SQLite
from modules import storage

# 🔐 Clave secreta para firmar tokens (⚠️ en producción usar variable de entorno)
SECRET_KEY = "mi_super_secreto"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Contexto de hash de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Dependencia para extraer token Bearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

# ==============================
# 🔑 Funciones de seguridad
# ==============================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si la contraseña ingresada coincide con el hash almacenado."""
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_user(username: str, password: str):
    """Busca usuario en SQLite y valida contraseña."""
    conn = storage.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, full_name, hashed_password, role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    # Do not close the global connection here

    if not row:
        return None

    db_user = {
        "username": row[0],
        "full_name": row[1],
        "hashed_password": row[2],
        "role": row[3],
    }

    if not verify_password(password, db_user["hashed_password"]):
        return None
    return db_user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Genera un JWT con expiración."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_token_from_request(request: Request, token: Optional[str] = Depends(oauth2_scheme)):
    """
    Intenta obtener el token del header 'Authorization'.
    Este es el método estándar de OAuth2.
    """
    return token

async def get_current_user(request: Request, token: Optional[str] = Depends(oauth2_scheme)):
    """Decodifica el JWT y obtiene el usuario actual de SQLite."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o token caducado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Si el token no viene en el header, intenta obtenerlo de la cookie.
    if token is None:
        token = request.cookies.get("access_token")

    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # Buscar usuario en DB
    conn = storage.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, full_name, hashed_password, role FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    # Do not close the global connection here

    if not row:
        raise credentials_exception

    return {
        "username": row[0],
        "full_name": row[1],
        "hashed_password": row[2],
        "role": row[3],
    }

def require_role(required_role: str):
    """Valida que el usuario tenga un rol específico."""
    def role_checker(user: dict = Depends(get_current_user)):
        if user["role"] != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso denegado. Se requiere rol: {required_role}",
            )
        return user
    return role_checker