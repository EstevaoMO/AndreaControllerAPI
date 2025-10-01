from fastapi import FastAPI, status, HTTPException
from fastapi.responses import JSONResponse
from supabase import create_client
from routers import chamadas, revistas, vendas

from settings.settings import importar_configs
from services.auth import pegar_usuario_admin

# Configurações iniciais
app = FastAPI(
    title="AndreaController API's Swagger",
    tags=["Global"]
)

st = importar_configs()

# Rotas globais
@app.get("/")
def home():
    return { "home": "" }

@app.get("/ping")
def ping():
    try:
        con = pegar_usuario_admin()
        if con:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content="Pong!"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_BAD_REQUEST,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )

@app.head("/ping", status_code=status.HTTP_200_OK)
def ping():
    try:
        con = pegar_usuario_admin()
        if con:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content="Pong!"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_BAD_REQUEST,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )

# Outras rotas
app.include_router(chamadas.router)
app.include_router(revistas.router)
app.include_router(vendas.router)
