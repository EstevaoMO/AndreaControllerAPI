from fastapi import APIRouter, UploadFile, HTTPException, File, Depends, status
from datetime import datetime
from supabase import Client
from typing import List, Dict, Any
import json
import re

from models.chamada_model import ChamadaDevolucaoResposta
from settings.settings import importar_configs
from services.auth import validar_token, pegar_usuario_admin
from services.extracao import processar_pdf_para_json
from services.extracao import extrair_texto_pdf_bytes

router = APIRouter(
    prefix="/chamadas",
    tags=["Chamadas"]
)

st = importar_configs()
URL_EXPIRATION_SECONDS = 30 * 24 * 60 * 60

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
        # Associa cada revista à chamada que está sendo criada
        for revista in revistas_para_inserir:
            revista['id_chamada_devolucao'] = id_chamada

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
    Recebe um ARQUIVO PDF, extrai a data, verifica duplicidade e, se for inédito,
    processa com IA, salva o arquivo e insere os dados no banco.
    """
    arquivo_bytes = await file.read()
    if not arquivo_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O arquivo enviado está vazio.")

    # ETAPA 1: Extrair a data do PDF via Regex, sem usar IA.
    texto_pdf = extrair_texto_pdf_bytes(arquivo_bytes)
    if not texto_pdf:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não foi possível extrair texto do PDF.")

    match = re.search(r"Data da chamada\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})", texto_pdf, re.IGNORECASE)
    if not match:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Padrão 'Data da chamada' não encontrado no PDF.")

    data_pdf_str = match.group(1)  # Formato DD/MM/AAAA
    try:
        # Converte a data para o formato do banco de dados (YYYY-MM-DD)
        data_pdf_iso = datetime.strptime(data_pdf_str, "%d/%m/%Y").date().isoformat()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Data encontrada no PDF está em formato inválido: {data_pdf_str}")

    # ETAPA 2: Buscar as datas-limite já existentes para este usuário.
    try:
        resposta = (
            supabase_admin.table("chamadasdevolucao")
            .select("data_limite")
            .eq("id_usuario", user["sub"])
            .execute()
        )
        # O Supabase retorna datas como strings no formato 'YYYY-MM-DD'
        datas_limite_existentes = [item["data_limite"] for item in resposta.data if "data_limite" in item]
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao buscar datas-limite do usuário: {e}")

    # ETAPA 3: Verificar se a data extraída já existe. Se sim, interromper.
    if data_pdf_iso in datas_limite_existentes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe uma chamada cadastrada para a data-limite {data_pdf_iso}."
        )

    # ETAPA 4: Somente se a data for nova, chamar o Gemini para processar o conteúdo.
    try:
        chamada_json = processar_pdf_para_json(arquivo_bytes)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Erro ao processar o conteúdo do PDF com a IA: {e}")

    # Validação do JSON retornado pela IA
    if "chamadasdevolucao" not in chamada_json or "revistas" not in chamada_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O JSON retornado pela IA é inválido. Faltam chaves 'chamadasdevolucao' ou 'revistas'."
        )

    # ETAPA 5: Fazer o upload do arquivo PDF para o Storage.
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    nome_arquivo_original = re.sub(r'[^a-zA-Z0-9.\-_]', '_', file.filename) # Limpa caracteres inválidos
    caminho_arquivo = f"{user['sub']}/{timestamp}_{nome_arquivo_original}"

    try:
        supabase_admin.storage.from_(st.BUCKET).upload(
            path=caminho_arquivo,
            file=arquivo_bytes,
            file_options={"content-type": file.content_type or "application/pdf"}
        )
        assinatura = supabase_admin.storage.from_(st.BUCKET).create_signed_url(caminho_arquivo, URL_EXPIRATION_SECONDS)
        url_assinada = assinatura.get("signedURL")
        if not url_assinada:
            raise ValueError("A resposta da URL assinada não contém a chave 'signedURL'.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao salvar o arquivo no storage: {e}")

    # ETAPA 6: Inserir a chamada de devolução no banco de dados.
    try:
        cd = chamada_json.get("chamadasdevolucao")

        # Garante que a data do PDF seja a usada (fonte da verdade)
        dados_chamada = {
            "id_usuario": user["sub"],
            "ponto_venda_id": cd.get("ponto_venda_id"),
            "data_limite": data_pdf_iso,
            "url_documento": url_assinada,
            "status": "aberta"
        }

        resposta_insert = supabase_admin.table("chamadasdevolucao").insert(dados_chamada).execute()
        chamada_criada = resposta_insert.data[0]
        id_chamada_criada = chamada_criada["id_chamada_devolucao"]

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Erro ao preparar ou inserir dados da chamada: {e}")

    # ETAPA 7: Inserir as revistas associadas à chamada.
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


@router.get("/datas-limite", summary="Listar datas-limite das chamadas de encalhe do usuário")
async def listar_datas_limite_chamadas(user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)):
    """
    Lista todas as datas-limite das chamadas de encalhe do usuário autenticado.
    """
    try:
        resposta = (
            supabase_admin.table("chamadasdevolucao")
            .select("data_limite")
            .eq("id_usuario", user["sub"])
            .order("data_limite", desc=True)
            .execute()
        )
        datas = [item["data_limite"] for item in resposta.data if "data_limite" in item]
        return {
            "data": datas,
            "message": "Datas-limite das chamadas de encalhe listadas com sucesso."
        }
    except Exception as e:
        print(f"Erro ao buscar datas-limite no Supabase: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro ao buscar as datas-limite das chamadas de encalhe."
        )