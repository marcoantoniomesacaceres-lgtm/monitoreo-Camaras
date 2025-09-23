from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# 🔐 Clave secreta para firmar tokens (en producción usar env variable!)
SECRET_KEY = "mi_super_secreto"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Contraseñas encriptadas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Simulación de base de datos de usuarios
fake_users_db = {
    "admin": {
        "username": "admin",
        "full_name": "Administrador del sistema",
        "hashed_password": pwd_context.hash("admin123"),
        "role": "admin",
    },
    "operador": {
        "username": "operador",
        "full_name": "Operador de cámaras",
        "hashed_password": pwd_context.hash("operador123"),
        "role": "operator",
    },
    "viewer": {
        "username": "viewer",
        "full_name": "Visualizador",
        "hashed_password": pwd_context.hash("viewer123"),
        "role": "viewer",
    },
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Verificar contraseña
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# Autenticación de usuario
def authenticate_user(username: str, password: str):
    user = fake_users_db.get(username)
    if not user or not verify_password(password, user["hashed_password"]):
        return None
    return user

# Crear token JWT
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Obtener usuario desde token
def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = fake_users_db.get(username)
    if user is None:
        raise credentials_exception
    return user

# Verificar rol
def require_role(required_role: str):
    def role_checker(user: dict = Depends(get_current_user)):
        if user["role"] != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso denegado. Se requiere rol: {required_role}",
            )
        return user
    return role_checker
