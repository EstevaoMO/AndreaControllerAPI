from fastapi import APIRouter, UploadFile, HTTPException, File, Depends, status, Path
from datetime import datetime
from supabase import Client
from typing import List, Dict, Any
import json

from models.chamada_model import ChamadaDevolucaoResposta
from settings.settings import importar_configs
from services.auth import validar_token, pegar_usuario_admin
from services.extracao_entrada import processar_pdf_para_json
from services.extracao import extrair_dados_entrada_local
from routers.revistas import pegar_revistas

# id_revista': None, 'nome': 'ALMANAQUE DE HISTORIAS CURTAS TURMA DA MONICA', 'numero_edicao': 16, 'qtd_estoque': 1, 'preco_capa': 11.9, 'url_revista': None
# {'id_nota_entrega': None, 'id_usuario': None, 'ponto_venda_id': 48507, 'nota_entrega_id': 1049, 'data': '2025-11-08', 'url_documento': None}


router = APIRouter(
    prefix="/entregas",
    tags=["Entregas"]
)

st = importar_configs()
URL_EXPIRATION_SECONDS = 30 * 24 * 60 * 60


def _cadastrar_revistas_db(entrega_json: Dict[str, Any], supabase_admin: Client, id_entrega_criada: str) -> tuple[int, int]:
    """
    Processa os dados das revistas do JSON e os insere/atualiza em lote.
    - Se a revista (nome + edição) existe, SOMA o estoque.
    - Se não existe, CRIA a revista com o estoque inicial.
    Retorna (novas_revistas_criadas, revistas_atualizadas).
    """
    lista_revistas_json = entrega_json.get("revistas", [])

    if not lista_revistas_json:
        return (0, 0)

    revistas_banco = pegar_revistas()
    revistas_existentes = revistas_banco.data if revistas_banco and revistas_banco.data else []

    lookup_revistas: Dict[tuple[str, str], dict] = {}
    for rev in revistas_existentes:
        try:
            nome_norm = str(rev.get("nome", "")).strip().lower()
            edicao_str = str(rev.get("numero_edicao", "0"))
            if nome_norm:
                lookup_revistas[(nome_norm, edicao_str)] = rev
        except Exception as e:
            print(f"Aviso: Ignorando revista do banco com dados inválidos: {rev.get('id_revista')} - {e}")

    inseridas = 0
    atualizadas = 0

    for revista_data in lista_revistas_json:
        try:
            nome = str(revista_data.get("nome", "")).strip()
            if not nome:
                print("Aviso: Ignorando revista sem nome no JSON.")
                continue

            nome_normalizado = nome.lower()


            numero_edicao_json = revista_data.get("numero_edicao")
            if numero_edicao_json is None:
                numero_edicao_str = "0"
                numero_edicao_int = 0
            else:
                numero_edicao_str = str(int(numero_edicao_json))
                numero_edicao_int = int(numero_edicao_json)

            qtd_nova = int(revista_data.get("qtd_estoque") or 0)
            if qtd_nova < 0:
                qtd_nova = 0

            preco_capa_str = str(revista_data.get("preco_capa", "0.0")).replace(',', '.')
            preco_capa = float(preco_capa_str)

            id_revista_processada = None

            chave_busca = (nome_normalizado, numero_edicao_str)
            revista_existente = lookup_revistas.get(chave_busca)

            if revista_existente:
                try:
                    id_revista_existente = revista_existente["id_revista"]
                    estoque_atual = int(revista_existente.get("qtd_estoque") or 0)
                    novo_estoque = estoque_atual + qtd_nova

                    supabase_admin.table("revistas").update(
                        {"qtd_estoque": novo_estoque}
                    ).eq("id_revista", id_revista_existente).execute()

                    id_revista_processada = id_revista_existente
                    atualizadas += 1

                    lookup_revistas[chave_busca]["qtd_estoque"] = novo_estoque

                except Exception as e:
                    print(f"ERRO: Falha ao ATUALIZAR estoque para '{nome}' (Ed: {numero_edicao_str}). Erro: {e}")
                    continue

            else:
                try:
                    revista_para_inserir = {
                        "nome": nome,
                        "numero_edicao": numero_edicao_int,
                        "qtd_estoque": qtd_nova,
                        "preco_capa": preco_capa,
                        "url_revista": revista_data.get("url_revista")
                    }

                    revista_inserida_resp = supabase_admin.table("revistas").insert(revista_para_inserir).execute()

                    nova_revista = revista_inserida_resp.data[0]
                    id_revista_processada = nova_revista["id_revista"]
                    inseridas += 1

                    lookup_revistas[chave_busca] = nova_revista

                except Exception as e:
                    print(f"ERRO: Falha ao INSERIR nova revista '{nome}' (Ed: {numero_edicao_str}). Erro: {e}")
                    continue

            if id_revista_processada:
                try:
                    supabase_admin.table("revistas_documentos_entrega").insert({
                        "id_documento_entrega": id_entrega_criada,
                        "id_revista": id_revista_processada,
                        "qtd_entregue": qtd_nova,
                    }).execute()
                except Exception as e:
                    print(f"ERRO: Falha ao INSERIR RELAÇÃO para '{nome}' (ID: {id_revista_processada}). Erro: {e}")

        except (ValueError, TypeError) as e:
            print(f"Aviso: Ignorando revista com dados inválidos no JSON: {revista_data.get('nome')}. Erro: {e}")
            continue

    return (inseridas, atualizadas)


@router.post("/cadastrar-entrega", status_code=status.HTTP_201_CREATED)
async def cadastrar_chamada(file: UploadFile = File(...), user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)):
    """
    Recebe um ARQUIVO PDF, salva-o no storage, interpreta seu conteúdo
    e insere os dados da entrega e das revistas no banco.
    """
    arquivo_bytes = await file.read()
    if not arquivo_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O arquivo enviado está vazio.")

    try:
        (data_iso_local, pv_id_local) = extrair_dados_entrada_local(arquivo_bytes)

        resposta_duplicata = (
            supabase_admin.table("documentos_entrega")
            .select("id_documento_entrega")
            .eq("id_usuario", user["sub"])
            .eq("data_entrega", data_iso_local)
            .execute()
        )

        if resposta_duplicata.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Documento de entrega duplicado. Já existe um cadastro para o PDV {pv_id_local} na data {data_iso_local}.",
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Erro na pré-verificação do PDF: {e}")
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao verificar duplicatas: {e}")


    try:
        entrega_json = await processar_pdf_para_json(arquivo_bytes)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Erro ao processar PDF (IA): {str(e)}")

    if "notasentrega" not in entrega_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O conteúdo do JSON (IA) é inválido. A chave 'notasentrega' é obrigatória."
        )

    try:
        cd = entrega_json.get("notasentrega")
        if cd is None:
            raise KeyError("notasentrega")

        nota_id_gemini = cd.get("nota_entrega_id")
        data_gemini = cd.get("data")

        missing = []

        if nota_id_gemini is None:
            missing.append("nota_entrega_id (IA)")
        if data_gemini is None:
            missing.append("data (IA)")

        if missing:
            raise KeyError(f"Campos faltando em notasentrega (IA): {missing}")

        data_iso_gemini = datetime.strptime(data_gemini, "%Y-%m-%d").date().isoformat()


        dados_entrega = {
            "id_usuario": user["sub"],
            "data_entrega": data_iso_gemini,
        }

        resposta_insert = supabase_admin.table("documentos_entrega").insert(dados_entrega).execute()
        entrega_criada = resposta_insert.data[0]
        id_entrega_criada = entrega_criada["id_documento_entrega"]

    except KeyError as e:
        detail = f"Chave ausente no JSON (IA): {e}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    except ValueError as e:
        detail = f"Valor inválido no JSON (IA): {e}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    except HTTPException as e:
        raise e
    except Exception as e:
        detail = f"Erro ao inserir documento de entrega no banco: {e}"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


    revistas_inseridas, revistas_atualizadas = _cadastrar_revistas_db(entrega_json, supabase_admin, id_entrega_criada)

    return {
        "data": {
            "id_entrega": id_entrega_criada,
            "qtd_novas_revistas_criadas": revistas_inseridas,
            "qtd_revistas_com_estoque_atualizado": revistas_atualizadas,
        },
        "message": "Entrega criada e estoque de revistas atualizado com sucesso."
    }

@router.get("/listar-entradas-usuario")
async def listar_entradas_por_usuario(user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)):
    """
    Lista todas as entradas associadas ao usuário autenticado.
    """
    try:
        resposta = (
            supabase_admin.table("documentos_entrega")
            .select("*")
            .eq("id_usuario", user["sub"])
            .order("data_entrega", desc=True)
            .execute()
        )
        return resposta.data

    except Exception as e:
        print(f"Erro ao buscar entradas no Supabase: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro ao buscar as devoluções."
        )

@router.get("/{id_entrega}")
async def get_entrega_por_id(id_entrega: int = Path(..., title="ID do Documento de Entrega", ge=1), user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)):
    """
    Retorna os dados de um documento de entrega pelo ID,
    incluindo as revistas associadas (join).
    """
    try:
        resposta = (
            supabase_admin.table("documentos_entrega")
            .select("*, revistas_documentos_entrega(*, revistas(nome, numero_edicao, url_revista, codigo_barras))")
            .eq("id_documento_entrega", id_entrega)
            .eq("id_usuario", user["sub"])
            .single()
            .execute()
        )

        if not resposta.data:
            raise HTTPException(status_code=404, detail=f"Documento de entrega {id_entrega} não encontrado ou não pertence a este usuário.")

        return resposta.data

    except Exception as e:
        msg = str(e)
        if isinstance(e, HTTPException):
            raise e
        if "No rows" in msg or "multiple (or no) rows returned" in msg or "JSON object requested" in msg:
            raise HTTPException(status_code=404, detail=f"Documento de entrega {id_entrega} não encontrado ou não pertence a este usuário.")
        raise HTTPException(status_code=500, detail=msg)