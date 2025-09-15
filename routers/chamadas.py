from fastapi import APIRouter, UploadFile, HTTPException, File, Depends
from datetime import datetime
from supabase import Client, create_client

from settings.settings import importar_configs
from services.auth import validar_token
from services.ocr import OCRMockado

# Configurações iniciais
router = APIRouter(
    prefix="/chamada",
    tags=["Chamada"]
)

st = importar_configs()
supabase: Client = create_client(st.SUPABASE_URL, st.SUPABASE_API_KEY)

# Função de apoio para cadastro de chamada
def cadastrar_revistas(chamada_json: dict, supabase_client: Client):
    """
    Processa os dados das revistas do JSON e os insere em lote na tabela 'Revistas'.
    """
    revistas_para_inserir = []
    lista_revistas_json = chamada_json.get("revistas", [])

    if not lista_revistas_json:
        return { "status": "sem_revistas", "message": "Nenhuma revista encontrada no documento." }

    for revista_json in lista_revistas_json:
        try:
            edicao = int(revista_json.get("edicao", 0))
            estoque = int(revista_json.get("rep") or 0)
            preco_c = float(str(revista_json.get("pco_capa", "0.0")).replace(',', '.'))
            preco_l = float(str(revista_json.get("pco_liq", "0.0")).replace(',', '.'))
            cod_barras = str(revista_json.get("ean", "")).replace(" ", "")
        except (ValueError, TypeError) as e:
            print(f"Erro ao converter dados para a revista '{revista_json.get('produto')}': {e}")
            continue 

        revistas_para_inserir.append({
            "nome": revista_json.get("produto"),
            "apelido_revista": revista_json.get("subtitulo"),
            "numero_edicao": edicao,
            "codigo_barras": cod_barras,
            "qtd_estoque": estoque,
            "preco_capa": preco_c,
            "preco_liquido": preco_l,
        })
    
    if not revistas_para_inserir:
        raise HTTPException(status_code=400, detail="Nenhuma revista pôde ser processada com sucesso.")

    try:
        resposta = supabase_client.table("Revistas").insert(revistas_para_inserir).execute()
        
        if resposta.status_code not in [200, 201]:
             raise HTTPException(status_code=500, detail=f"Falha ao inserir revistas no banco de dados. Status: {resposta.status_code}")
        
        return resposta

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Um erro de banco de dados ocorreu: {str(e)}")


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
    resposta_cadastro_revistas = cadastrar_revistas(json_arquivo_lido)

    return { "status_upload": resposta_upload.status_code, 
            "status_insert": resposta_insert.status_code,
            "status_cadastro_revistas": resposta_cadastro_revistas
            }