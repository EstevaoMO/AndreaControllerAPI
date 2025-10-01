from fastapi import APIRouter, UploadFile, HTTPException, File, Depends, status
from datetime import datetime
from supabase import Client
from typing import List, Dict, Any
import json

from models.chamada_model import ChamadaDevolucaoResposta
from settings.settings import importar_configs
from services.auth import validar_token, pegar_usuario_admin
from services.extracao import processar_pdf_para_json



router = APIRouter(
    prefix="/chamadas",
    tags=["Chamadas"]
)

st = importar_configs()
URL_EXPIRATION_SECONDS = 30 * 24 * 60 * 60 


# Permissão de Admin para colocar arquivo no bucket
# Era aqui que estava dando problema, a lógica é que você precisa de permissão de adm para inserir dados em BUCKETs
# Usando a chave "service_key" conseguimos essa permissão, mas inserimos como um usuário diferente do usuário logado
# Por isso, dentro de 'docs', fiz os arquivos serem salvos dentro de uma pasta com o user_id
def _cadastrar_revistas_db(chamada_json: Dict[str, Any], supabase_admin: Client, id_chamada: int) -> int:
    """
    Processa os dados das revistas do JSON e os insere em lote na tabela 'revistas'.
    Retorna a quantidade de revistas inseridas com sucesso.
    """
    revistas_para_inserir = []
    lista_revistas_json = chamada_json.get("revistas", [])

    if not lista_revistas_json:
        return 0

    for revista_data in lista_revistas_json:
        try:
            preco_capa_str = str(revista_data.get("preco_capa", "0.0")).replace(',', '.')
            preco_liq_str = str(revista_data.get("preco_liquido", "0.0")).replace(',', '.')
            
            revistas_para_inserir.append({
                "nome": revista_data.get("nome"),
                "apelido_revista": revista_data.get("apelido_revista"),
                "numero_edicao": int(revista_data.get("numero_edicao", 0)),
                "codigo_barras": str(revista_data.get("codigo_barras", "")).strip(),
                "qtd_estoque": int(revista_data.get("qtd_estoque") or 0),
                "preco_capa": float(preco_capa_str),
                "preco_liquido": float(preco_liq_str),
            })
        except (ValueError, TypeError) as e:
            print(f"Aviso: Ignorando revista com dados inválidos: {revista_data.get('produto')}. Erro: {e}")
            continue

    if not revistas_para_inserir:
        return 0

    try:
        resposta_revistas = supabase_admin.table("revistas").insert(revistas_para_inserir).execute()
        return len(resposta_revistas.data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ocorreu um erro de banco de dados ao inserir as revistas: {str(e)}"
        )


@router.post("/cadastrar-chamada", status_code=status.HTTP_201_CREATED)
async def cadastrar_chamada(file: UploadFile = File(...), user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)):
    """
    Recebe um ARQUIVO JSON, salva-o no storage, interpreta seu conteúdo
    e insere os dados da chamada e das revistas no banco.
    """
    arquivo_bytes = await file.read()
    if not arquivo_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O arquivo enviado está vazio.")
    
    try:
        chamada_json = processar_pdf_para_json(arquivo_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O arquivo enviado não contém um JSON válido.")

    if "chamadasdevolucao" not in chamada_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O conteúdo do JSON é inválido. A chave 'chamadasdevolucao' é obrigatória."
        )


    # Carrega o arquivo json no Bucket, criando uma pasta com o user_id
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    caminho_arquivo = f"{user['sub']}/{timestamp}_{file.filename}"
    try:
        supabase_admin.storage.from_(st.BUCKET).upload(
            path=caminho_arquivo,
            file=arquivo_bytes,
            file_options={"content-type": file.content_type or "application/json"}
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao salvar o arquivo: {e}")

    try:
        assinatura = supabase_admin.storage.from_(st.BUCKET).create_signed_url(caminho_arquivo, URL_EXPIRATION_SECONDS)
        url_assinada = assinatura.get("signedURL")
        if not url_assinada:
            raise ValueError("A resposta da URL assinada não contém a chave 'signedURL'.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar URL para o documento: {e}")

    try:
        cd = chamada_json.get("chamadasdevolucao")
        if cd is None:
            raise KeyError("chamadasdevolucao")

        # campos esperados que você quer extrair
        pv_id = cd.get("ponto_venda_id")
        dl = cd.get("data_limite")

        missing = []
        if pv_id is None:
            missing.append("ponto_venda_id")
        if dl is None:
            missing.append("data_limite")

        if missing:
            raise KeyError(f"Campos faltando em chamadasdevolucao: {missing}")

        # Verifica tipo/valor de data_limite
        try:
            data_limite_dt = datetime.strptime(dl, "%Y-%m-%d")
        except Exception as e:
            raise ValueError(f"Formato inválido para data_limite: {dl}. Erro: {e}")

        dados_chamada = {
            "id_usuario": user["sub"],
            "ponto_venda_id": chamada_json["chamadasdevolucao"]["ponto_venda_id"],
            "data_limite": datetime.strptime(
                chamada_json["chamadasdevolucao"]["data_limite"], "%Y-%m-%d"
            ).date().isoformat(),
            "url_documento": url_assinada,
            "status": "aberta"
        }

        resposta_insert = supabase_admin.table("chamadasdevolucao").insert(dados_chamada).execute()
        chamada_criada = resposta_insert.data[0]
        id_chamada_criada = chamada_criada["id_chamada_devolucao"]

    except KeyError as e:
        detail = f"Chave ausente no JSON: {e}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    except ValueError as e:
        detail = f"Valor inválido no JSON: {e}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


    # AQUI ELE CADASTRA AS REVISTAS
    revistas_inseridas = _cadastrar_revistas_db(chamada_json, supabase_admin, id_chamada_criada)
    
    return {
        "data": {
            "id_chamada": id_chamada_criada,
            "url_documento": url_assinada,
            "qtd_revistas_cadastradas": revistas_inseridas
        },
        "message": "Chamada criada e revistas cadastradas com sucesso."
    }

@router.get("/listar-chamadas-usuario")
async def listar_chamadas_por_usuario(user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)):
    """
    Lista todas as chamadas de devolução associadas ao usuário autenticado.
    """
    try:
        resposta = (
            supabase_admin.table("chamadasdevolucao")
            .select("*")
            .eq("id_usuario", user["sub"])
            .order("data_limite", desc=True)
            .execute()
        )
        return {
            "data": resposta.data,
            "message": "Chamadas do usuário listadas com sucesso."
        }
    except Exception as e:
        print(f"Erro ao buscar chamadas no Supabase: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro ao buscar as chamadas de devolução."
        )