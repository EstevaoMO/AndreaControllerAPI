from fastapi import APIRouter, UploadFile, HTTPException, File, Depends, status, Path
from datetime import datetime
from supabase import Client
from typing import List, Dict, Any
import json

from models.chamada_model import ChamadaDevolucaoResposta
from settings.settings import importar_configs
from services.auth import validar_token, pegar_usuario_admin
from services.extracao_devolucao import processar_pdf_para_json
from services.extracao import extrair_dados_devolucao_local
from routers.revistas import pegar_revistas


router = APIRouter(
    prefix="/devolucoes",
    tags=["Devolucoes"]
)

st = importar_configs()

def _cadastrar_revistas_db(chamada_json: Dict[str, Any], supabase_admin: Client, id_devolucao_criada: str) -> tuple[int, int]:
    """
    Processa as revistas do JSON (da devolução).
    Lógica de Negócio (CONFORME SOLICITADO):
    1. Verifica por NOME e EDIÇÃO se a revista já existe no banco.
    2. SE EXISTIR: Pega o ID. NÃO FAZ NADA com a tabela 'revistas'.
    3. SE NÃO EXISTIR: Cria a revista (legada) com ESTOQUE 0. Pega o ID.
    4. Associa o ID (existente ou novo) à devolução na tabela 'revistas_chamadasdevolucao'.

    Retorna (novas_revistas_criadas, revistas_associadas_total).
    """
    lista_revistas_json = chamada_json.get("revistas", [])
    if not lista_revistas_json:
        return (0, 0)

    revistas_banco = pegar_revistas()
    revistas_existentes = revistas_banco.data if revistas_banco and revistas_banco.data else []

    lookup_revistas: Dict[tuple[str, str], dict] = {}
    for rev in revistas_existentes:
        try:
            nome_norm = str(rev.get("nome", "")).strip().lower()
            edicao_str = "0" if rev.get("numero_edicao") is None else str(rev.get("numero_edicao"))
            if nome_norm:
                lookup_revistas[(nome_norm, edicao_str)] = rev
        except Exception as e:
            print(f"Aviso: Ignorando revista do banco com dados inválidos: {rev.get('id_revista')} - {e}")


    novas_revistas_criadas = 0
    revistas_associadas = 0

    def inserir_revista_legada(revista):
        """
        Cria uma revista que não existe no banco (legada) com estoque 0.
        """
        try:
            nome_revista = revista.get("nome")
            edicao_revista = revista.get("numero_edicao")
            codigo_barras = str(revista.get("codigo_barras"))
            if codigo_barras and codigo_barras.isdigit():
                codigo_barras = codigo_barras.strip()[:13]
                if len(codigo_barras) != 13:
                    codigo_barras = None
            else:
                codigo_barras = None
            print(f"INFO: Revista '{nome_revista}' (Ed: {edicao_revista}) não encontrada. Criando como legada com estoque 0.")

            resposta_insert = supabase_admin.table("revistas").insert({
                "nome": nome_revista,
                "numero_edicao": edicao_revista,
                "codigo_barras": codigo_barras,
                "qtd_estoque": 0,
                "preco_capa": revista.get("preco_capa", 0.0),
                "preco_liquido": revista.get("preco_liquido", 0.0)
            }).execute()

            revista_criada = resposta_insert.data[0]
            return revista_criada
        except Exception as e:
            if "violates unique constraint" in str(e):
                print(f"AVISO: Revista legada '{nome_revista}' não criada, provável código de barras duplicado. Erro: {e}")
                resp = supabase_admin.table("revistas").select("id_revista").eq("codigo_barras", revista.get("codigo_barras")).execute()
                if resp.data:
                    return resp.data[0]
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao inserir revista legada: {e}; Revista: {revista}")

    def inserir_relacao_chamada(id_revista, revista):
        """Associa a revista à devolução com a quantidade a ser devolvida."""
        try:
            qtd_a_devolver = revista.get("qtd_estoque", 0)

            supabase_admin.table("revistas_chamadasdevolucao").insert({
                "id_chamada_devolucao": id_devolucao_criada,
                "id_revista": id_revista,
                "data_recebimento": revista.get("data_entrega"),
                "qtd_recebida": qtd_a_devolver,
                "qtd_a_devolver": qtd_a_devolver,
            }).execute()
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao inserir relação entre revista e chamada: {e}; ID da revista: {id_revista}; Revista: {revista}")

    for revista_json in lista_revistas_json:
        try:
            nome = str(revista_json.get("nome", "")).strip()
            if not nome:
                print("Aviso: Ignorando revista sem nome no JSON.")
                continue

            nome_normalizado = nome.lower()

            numero_edicao_json = revista_json.get("numero_edicao")
            edicao_str = "0" if numero_edicao_json is None else str(int(numero_edicao_json))

            id_revista_final = None

            chave_busca = (nome_normalizado, edicao_str)
            revista_existente = lookup_revistas.get(chave_busca)

            if revista_existente:
                id_revista_final = revista_existente["id_revista"]

            else:
                nova_revista = inserir_revista_legada(revista_json)
                id_revista_final = nova_revista["id_revista"]
                novas_revistas_criadas += 1

                lookup_revistas[chave_busca] = nova_revista

            if id_revista_final:
                inserir_relacao_chamada(id_revista_final, revista_json)
                revistas_associadas += 1

        except (ValueError, TypeError) as e:
            print(f"Aviso: Ignorando revista com dados inválidos no JSON: {revista_json.get('nome')}. Erro: {e}")
            continue
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao processar revista: {e}; Revista: {revista_json}")

    return (novas_revistas_criadas, revistas_associadas)


@router.post("/cadastrar-devolucao", status_code=status.HTTP_201_CREATED)
async def cadastrar_devolucao(file: UploadFile = File(...), user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)):
    """
    ETAPA 1: Recebe um ARQUIVO PDF, usa IA para extrair dados,
    e salva o registro da tarefa de devolução com status 'aberta'.
    NÃO ATUALIZA O ESTOQUE PRINCIPAL.
    """
    arquivo_bytes = await file.read()
    if not arquivo_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O arquivo enviado está vazio.")

    try:
        data_limite_iso_local = extrair_dados_devolucao_local(arquivo_bytes)

        resposta_duplicata = (
            supabase_admin.table("chamadasdevolucao")
            .select("id_chamada_devolucao")
            .eq("id_usuario", user["sub"])
            .eq("data_limite", data_limite_iso_local)
            .execute()
        )

        if resposta_duplicata.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Chamada de devolução duplicada. Já existe um cadastro com data limite {data_limite_iso_local}.",
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Erro na pré-verificação do PDF: {e}")
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao verificar duplicatas: {e}")


    try:
        chamada_json = await processar_pdf_para_json(arquivo_bytes)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Erro ao processar PDF (IA): {str(e)}")

    if "chamadasdevolucao" not in chamada_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O conteúdo do JSON (IA) é inválido. A chave 'chamadasdevolucao' é obrigatória."
        )

    try:
        cd = chamada_json.get("chamadasdevolucao")
        if cd is None:
            raise KeyError("chamadasdevolucao")

        dl_gemini = cd.get("data_limite")

        if not dl_gemini:
            raise KeyError(f"Campo 'data_limite' é obrigatório (IA).")


        dados_chamada = {
            "id_usuario": user["sub"],
            "data_limite": datetime.strptime(dl_gemini, "%Y-%m-%d").date().isoformat(),
            "status": "aberta"
        }

        resposta_insert = supabase_admin.table("chamadasdevolucao").insert(dados_chamada).execute()
        chamada_criada = resposta_insert.data[0]
        id_devolucao_criada = chamada_criada["id_chamada_devolucao"]

    except (KeyError, ValueError) as e:
        detail = f"Erro ao processar dados da devolução (IA): {e}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    except HTTPException as e:
        raise e
    except Exception as e:
        detail = f"Erro geral ao inserir devolução: {e}"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)

    revistas_inseridas, revistas_associadas = _cadastrar_revistas_db(chamada_json, supabase_admin, id_devolucao_criada)

    return {
        "data": {
            "id_devolucao": id_devolucao_criada,
            "qtd_revistas_legadas_criadas": revistas_inseridas,
            "qtd_revistas_na_devolucao": revistas_associadas,
        },
        "message": "Devolução (Chamada) registrada com status 'aberta'. Estoque não alterado."
    }

@router.post("/{id_devolucao}/confirmar", status_code=status.HTTP_200_OK)
async def confirmar_devolucao(
    id_devolucao: int = Path(..., title="ID da Devolução a ser confirmada", ge=1),
    user: dict = Depends(validar_token),
    supabase_admin: Client = Depends(pegar_usuario_admin)
):
    """
    ETAPA 2: Confirma uma devolução (tarefa concluída).
    APENAS atualiza o status da devolução para 'fechada'.
    NÃO GERE-NCIA MAIS O ESTOQUE.
    """

    try:
        resposta_update = supabase_admin.table("chamadasdevolucao").update(
            {"status": "fechada"}
        ).eq("id_chamada_devolucao", id_devolucao).eq("id_usuario", user["sub"]).execute()

        if not resposta_update.data:
             raise HTTPException(status_code=404, detail="Devolução não encontrada ou não pertence a este usuário.")

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Erro ao confirmar a devolução: {str(e)}")

    return {
        "data": {
            "id_devolucao_confirmada": id_devolucao,
            "novo_status": "fechada"
        },
        "message": "Devolução confirmada e movida para 'fechada'."
    }


@router.get("/listar-devolucoes-usuario")
async def listar_devolucoes_por_usuario(user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)):
    """
    Lista todas as devoluções (antigas chamadas) associadas ao usuário autenticado.
    """
    try:
        resposta = (
            supabase_admin.table("chamadasdevolucao")
            .select("*")
            .eq("id_usuario", user["sub"])
            .order("data_limite", desc=True)
            .execute()
        )
        return resposta.data

    except Exception as e:
        print(f"Erro ao buscar devoluções no Supabase: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro ao buscar as devoluções."
        )

@router.get("/{id_devolucao}")
async def get_devolucao_por_id(id_devolucao: int, user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)):
    """
    Retorna os dados de uma devolução (antiga chamada) pelo ID,
    incluindo as revistas associadas.
    O frontend pode usar isso para a "Consulta".
    """
    try:
        resposta = (
            supabase_admin.table("chamadasdevolucao")
            .select("*, revistas_chamadasdevolucao(*, revistas(nome, numero_edicao))")
            .eq("id_chamada_devolucao", id_devolucao)
            .eq("id_usuario", user["sub"])
            .single()
            .execute()
        )

        if not resposta.data:
            raise HTTPException(status_code=404, detail=f"Devolução {id_devolucao} não encontrada ou não pertence a este usuário.")

        return resposta.data

    except Exception as e:
        msg = str(e)
        if isinstance(e, HTTPException):
            raise e
        if "No rows" in msg or "multiple (or no) rows returned" in msg or "JSON object requested" in msg:
            raise HTTPException(status_code=404, detail=f"Devolução {id_devolucao} não encontrada ou não pertence a este usuário.")
        raise HTTPException(status_code=500, detail=msg)