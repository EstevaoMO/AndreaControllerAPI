# Importe o que for necessário no topo do arquivo
from fastapi import APIRouter, UploadFile, HTTPException, File, Depends
from datetime import datetime
from supabase import Client, create_client
from typing import List, Optional
from pydantic import BaseModel

from settings.settings import importar_configs
from services.auth import validar_token
from services.ocr import OCRMockado

# --- Configuração do Router (sugestão de mudança para o plural) ---
router = APIRouter(
    prefix="/chamadas", # Sugestão: "/chamadas" em vez de "/chamada"
    tags=["Chamada"]
)

# Modelo Pydantic para resposta do GET
class ChamadaDevolucaoResponse(BaseModel):
    id: Optional[int]
    id_usuario: Optional[str]
    ponto_venda_id: Optional[str]
    data_limite: Optional[str]
    url_documento: Optional[str]
    status: Optional[str]

st = importar_configs()
supabase: Client = create_client(st.SUPABASE_URL, st.SUPABASE_API_KEY)

# Função de apoio para cadastro de chamada
def cadastrar_revistas(chamada):
    pass

# --- Sua rota POST (ajustada para o novo prefixo) ---
@router.post("/") # Alterado de "/cadastrar-chamada" para "/"
async def cadastrar_chamada(file: UploadFile = File(...), user: dict = Depends(validar_token)):
    # ... seu código do POST continua o mesmo aqui ...
    # ...
    # ...
    arquivo = await file.read()
    caminho_arquivo = f"{st.BUCKET}/{file.filename}"
    
    # Envia arquivo para o Supabase Storage
    resposta_upload = supabase.storage.from_(st.BUCKET).upload(
        caminho_arquivo,
        arquivo,
        { "contentType": file.content_type or "application/octet-stream" }
    )

    # Assina um tempo para a URL de acesso e a retorna para escrever no banco
    assinatura = supabase.storage.from_(st.BUCKET).create_signed_url(
        caminho_arquivo,
        2_592_000 # 30 dias
    )
    url_assinada = assinatura.get("signedUrl")

    if not url_assinada:
        raise HTTPException(status_code=500, detail="Falha ao gerar URL assinada")

    # Pega a imagem e transcreve para inserir os dados da chamada no banco
    json_arquivo_lido = OCRMockado(arquivo)
    dados_chamada = {
        "id_usuario": user["sub"],
        "ponto_venda_id": json_arquivo_lido["chamada_encalhe"]["ponto"],
        "data_limite": datetime.strptime(json_arquivo_lido["chamada_encalhe"]["data_da_chamada"], "%d/%m/%Y").strftime("%Y-%m-%d"),
        "url_documento": url_assinada,
        "status": "aberta"
    }

    resposta_insert = (
        supabase.table("chamadasdevolucao")
        .insert(dados_chamada)
        .execute()
    )

    # Cadastra as revistas no banco
    cadastro_revistas = cadastrar_revistas(json_arquivo_lido)

    return { "status_upload": resposta_upload.status_code, "status_insert": resposta_insert.status_code }


@router.get("/", response_model=List[ChamadaDevolucaoResponse])
async def listar_chamadas_por_usuario(user: dict = Depends(validar_token)):
    """
    Lista todas as chamadas de devolução associadas ao usuário autenticado.
    """
    user_id = user["sub"]

    try:
        # Executa a consulta no Supabase para buscar as chamadas do usuário
        resposta = (
            supabase.table("chamadasdevolucao")
            .select("*")  # Seleciona todas as colunas
            .eq("id_usuario", user_id)  # Filtra pelo ID do usuário logado
            .order("data_limite", desc=True) # Opcional: ordena pela data mais recente
            .execute()
        )

        # O resultado da consulta fica no atributo 'data'
        return resposta.data

    except Exception as e:
        # Tratamento de erro genérico para falhas na comunicação com o banco
        print(f"Erro ao buscar chamadas no Supabase: {e}") # Logar o erro é uma boa prática
        raise HTTPException(
            status_code=500,
            detail="Ocorreu um erro ao buscar as chamadas de devolução."
        )