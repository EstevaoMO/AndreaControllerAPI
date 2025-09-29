from fastapi import FastAPI
from routers import chamadas, revistas, vendas

# Configurações iniciais
app = FastAPI(
    title="AndreaController API's Swagger",
    tags=["Global"]
)

# Rotas globais
@app.get("/")
def home():
    return { "home": "" }

@app.get("/ping")
def ping():
    return { "ping": "pong!" }

# Outras rotas
app.include_router(chamadas.router)
app.include_router(revistas.router)
app.include_router(vendas.router)