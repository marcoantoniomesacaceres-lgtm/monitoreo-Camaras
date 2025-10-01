from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import timedelta

# Importa las funciones de ayuda desde el nuevo archivo auth.py
from auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

router = APIRouter()
templates = Jinja2Templates(directory="dashboard/templates")


@router.post("/login")
async def login(request: Request):
    """
    Acepta:
      - application/x-www-form-urlencoded (desde tu login.html con URLSearchParams)
      - application/json
    Devuelve JSON con access_token y también setea cookie (secure=False en dev).
    """
    # Leer credenciales
    username, password = None, None
    try:
        ctype = request.headers.get("content-type", "")
        if "application/json" in ctype:
            body = await request.json()
            username = body.get("username")
            password = body.get("password")
        else:
            form = await request.form()
            username = form.get("username")
            password = form.get("password")
    except Exception:
        raise HTTPException(status_code=400, detail="Formato inválido")

    if not username or not password:
        raise HTTPException(status_code=400, detail="username y password requeridos")

    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generar token con expiración
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["username"], "role": user.get("role", "user")},
        expires_delta=access_token_expires,
    )

    response = JSONResponse(content={
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"username": user["username"], "role": user.get("role", "user")}
    })

    # Guardar token en cookie (en prod secure=True)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="Lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )
    return response

@router.get("/login", response_class=HTMLResponse, tags=["Pages"])
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/", response_class=HTMLResponse, tags=["Pages"])
async def root(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/dashboard", response_class=HTMLResponse, tags=["Pages"])
async def dashboard(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {"request": request, "username": user.get("username", "Usuario")})

@router.post("/dashboard", response_class=HTMLResponse, tags=["Pages"])
async def dashboard_post(request: Request, user: dict = Depends(get_current_user)):
    return templates.TemplateResponse("index.html", {"request": request, "username": user.get("username", "Usuario")})

@router.get("/secure-data", tags=["Data"])
async def secure_data(user=Depends(get_current_user)):
    return {"data": f"Hola {user['username']} ({user['role']}), este es un endpoint protegido"}