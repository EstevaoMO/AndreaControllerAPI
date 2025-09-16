from fastapi import APIRouter, UploadFile, HTTPException, File, Depends
from datetime import datetime
from supabase import Client, create_client

from settings.settings import importar_configs
from services.auth import validar_token
from services.ocr import OCRMockado
from models.chamada_model import Chamada

# Configurações iniciais
router = APIRouter(
    prefix="/chamada",
    tags=["Chamada"]
)

st = importar_configs()
supabase: Client = create_client(st.SUPABASE_URL, st.SUPABASE_API_KEY)

# Função de apoio para cadastro de chamada
def cadastrar_revistas(chamada):
    pass

# Rotas
@router.post("/cadastrar-chamada")
async def cadastrar_chamada(file: UploadFile = File(...), user: dict = Depends(validar_token)):
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

@router.get("/{id}", response_model=Chamada)
async def get_chamada(id: int, user: dict = Depends(validar_token)):
    """
    Retorna os dados de uma chamada de devolução pelo ID.
    """
    try:
        resposta = (
            supabase.table("chamadasdevolucao")
            .select("*")
            .eq("id", id)
            .single()
            .execute()
        )

        if not resposta.data:
            raise HTTPException(status_code=404, detail=f"Chamada {id} não encontrada")

        return resposta.data

    except Exception as e:
        msg = str(e)
        if "No rows" in msg or "multiple (or no) rows returned" in msg:
            raise HTTPException(status_code=404, detail=f"Chamada {id} não encontrada")
        raise HTTPException(status_code=500, detail=msg)