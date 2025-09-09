from fastapi import FastAPI, UploadFile, File, Depends
from funcoes import OCRMockado, validar_token

app = FastAPI()

@app.get("/ping")
def ping():
    return {"ping": "pong!"}

@app.post("/cadastrar-chamada")
async def cadastrar_chamada(file: UploadFile = File(...), user: dict = Depends(validar_token)):
    arquivo = await file.read()
    
    json_arquivo_lido = OCRMockado(arquivo)

    # Implementar a lógica para salvar o JSON no banco de dados aqui

    return {"status": "Chamada cadastrada com sucesso!"}