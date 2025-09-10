from fastapi import FastAPI, UploadFile, File, Depends
from datetime import datetime
from os import getenv
from dotenv import load_dotenv
import requests

from servicos.ocr import OCRMockado
from servicos.auth import validar_token


# Configurações iniciais
app = FastAPI()

load_dotenv()
URL = getenv("SUPABASE_URL")
CHAVE_ACESSO = getenv("SUPABASE_API_KEY")
BUCKET = getenv("NOME_BUCKET")

headers_insert = {
    "apikey": CHAVE_ACESSO,
    "Authorization": f"Bearer {CHAVE_ACESSO}",
    "Content-Type": "application/json"
}

headers_storage = {
    "Authorization": f"Bearer {CHAVE_ACESSO}",
    "apikey": CHAVE_ACESSO,
    "Content-Type": "application/octet-stream"
}


# Rotas principais
@app.get("/ping")
def ping():
    return {"ping": "pong!"}

@app.post("/cadastrar-chamada")
async def cadastrar_chamada(file: UploadFile = File(...), user: dict = Depends(validar_token)):
    arquivo = await file.read()
    
    # Envia arquivo para o Supabase Storage
    caminho_arquivo = f"{BUCKET}/{file.filename}"
    url_doc = f"{URL}/storage/v1/object/{caminho_arquivo}"
    resposta_upload = requests.post(url_doc, headers=headers_storage, data=arquivo)

    # Assina um tempo para a URL de acesso e a retorna para escrever no banco
    url_assinada = f"{URL}/storage/v1/object/sign/{caminho_arquivo}"
    tempo_expiracao = {"expiresIn": 2592000}
    resposta = requests.post(url_assinada, headers=headers_insert, json=tempo_expiracao)
    url_gerada = resposta.json().get("signedURL")

    # Pega a imagem e transcreve para inserir os dados da chamada no banco
    json_arquivo_lido = OCRMockado(arquivo)
    dados_chamada = {
        "id_usuario": user["sub"],
        "ponto_venda_id": json_arquivo_lido["chamada_encalhe"]["ponto"],
        "data_limite": datetime.strptime(json_arquivo_lido["chamada_encalhe"]["data_da_chamada"], "%d/%m/%Y").strftime("%Y-%m-%d"),
        "url_documento": url_gerada,
        "status": "aberta"
    }

    URL_formatada = URL + "/rest/v1/chamadasdevolucao"
    resposta_insert = requests.post(URL_formatada, headers=headers_insert, json=dados_chamada)

    return { "status_upload": resposta_upload.status_code, "status_insert": resposta_insert.status_code}