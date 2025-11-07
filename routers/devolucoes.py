from fastapi import APIRouter, UploadFile, HTTPException, File, Depends, status, Path
from datetime import datetime
from supabase import Client
from typing import List, Dict, Any
import json

from models.chamada_model import ChamadaDevolucaoResposta
from settings.settings import importar_configs
from services.auth import validar_token, pegar_usuario_admin
# Importa a extração do Gemini (como antes)
from services.extracao_devolucao import processar_pdf_para_json
# [NOVO] Importa a extração local (PyPDF + Regex)
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

    # 1. Buscar revistas existentes e criar um mapa de busca
    revistas_banco = pegar_revistas()
    revistas_existentes = revistas_banco.data if revistas_banco and revistas_banco.data else []

    # O mapa usa (nome_normalizado, edicao_str) como chave para busca rápida
    lookup_revistas: Dict[tuple[str, str], dict] = {}
    for rev in revistas_existentes:
        try:
            nome_norm = str(rev.get("nome", "")).strip().lower()
            # Trata edições nulas como "0" para consistência na chave
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
            print(f"INFO: Revista '{nome_revista}' (Ed: {edicao_revista}) não encontrada. Criando como legada com estoque 0.")

            resposta_insert = supabase_admin.table("revistas").insert({
                "nome": nome_revista,
                "numero_edicao": edicao_revista,
                "codigo_barras": revista.get("codigo_barras"), # Salva se a IA extraiu
                "qtd_estoque": 0, # <-- LÓGICA CORRETA: Estoque é 0
                "preco_capa": revista.get("preco_capa", 0.0),
                "preco_liquido": revista.get("preco_liquido", 0.0)
            }).execute()

            revista_criada = resposta_insert.data[0]
            return revista_criada
        except Exception as e:
            # Pega erros de violação de constraint (ex: codigo_barras duplicado)
            if "violates unique constraint" in str(e):
                print(f"AVISO: Revista legada '{nome_revista}' não criada, provável código de barras duplicado. Erro: {e}")
                # Tenta buscar pelo código de barras como alternativa
                resp = supabase_admin.table("revistas").select("id_revista").eq("codigo_barras", revista.get("codigo_barras")).execute()
                if resp.data:
                    return resp.data[0] # Retorna a revista que já tem aquele código

            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao inserir revista legada: {e}; Revista: {revista}")

    def inserir_relacao_chamada(id_revista, revista):
        """Associa a revista à devolução com a quantidade a ser devolvida."""
        try:
            # 'qtd_estoque' do JSON (extraído da coluna 'Rep') é a qtd a devolver
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

    # 2. Iterar sobre as revistas do JSON (da Devolução)
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

            # --- Lógica Principal: Verificar se existe ---
            chave_busca = (nome_normalizado, edicao_str)
            revista_existente = lookup_revistas.get(chave_busca)

            if revista_existente:
                # --- CASO 1: REVISTA EXISTE ---
                # Apenas pega o ID. Não faz NADA com o estoque.
                id_revista_final = revista_existente["id_revista"]

            else:
                # --- CASO 2: REVISTA NÃO EXISTE ---
                # Insere a nova revista (legada) no banco com estoque 0
                nova_revista = inserir_revista_legada(revista_json)
                id_revista_final = nova_revista["id_revista"]
                novas_revistas_criadas += 1

                # Adiciona ao mapa local para evitar duplicatas na mesma execução
                lookup_revistas[chave_busca] = nova_revista

            # --- 3. Associar à Tabela de Relacionamento ---
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
        # --- [NOVO] INÍCIO DA PRÉ-VERIFICAÇÃO LOCAL ---
        # 1. Extrai data localmente (sem Gemini)
        data_limite_iso_local = extrair_dados_devolucao_local(arquivo_bytes)

        # 2. Verifica duplicatas no banco
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
        # Falha na extração local (PDF ilegível ou formato inesperado)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Erro na pré-verificação do PDF: {e}")
    except HTTPException as e:
        raise e # Propaga a exceção 409
    except Exception as e:
        # Falha na consulta de verificação
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao verificar duplicatas: {e}")
    # --- [NOVO] FIM DA PRÉ-VERIFICAÇÃO LOCAL ---


    # --- Processamento Gemini (só ocorre se a pré-verificação passar) ---
    try:
        # 1. Chama o Gemini para extração completa
        chamada_json = processar_pdf_para_json(arquivo_bytes)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Erro ao processar PDF (IA): {str(e)}")

    if "chamadasdevolucao" not in chamada_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O conteúdo do JSON (IA) é inválido. A chave 'chamadasdevolucao' é obrigatória."
        )

    # 2. Insere o documento principal (com dados do Gemini)
    try:
        cd = chamada_json.get("chamadasdevolucao")
        if cd is None:
            raise KeyError("chamadasdevolucao")

        dl_gemini = cd.get("data_limite")

        if not dl_gemini:
            raise KeyError(f"Campo 'data_limite' é obrigatório (IA).")

        # [REMOVIDO] Bloco de verificação de duplicata movido para cima.

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

    # 3. Cadastra as revistas (lógica inalterada)
    revistas_inseridas, revistas_associadas = _cadastrar_revistas_db(chamada_json, supabase_admin, id_devolucao_criada)

    return {
        "data": {
            "id_devolucao": id_devolucao_criada,
            "qtd_revistas_legadas_criadas": revistas_inseridas,
            "qtd_revistas_na_devolucao": revistas_associadas,
        },
        "message": "Devolução (Chamada) registrada com status 'aberta'. Estoque não alterado."
    }

# --- ENDPOINT ETAPA 2 (LÓGICA ALTERADA CONFORME SEU PEDIDO) ---
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
        # 1. Apenas atualiza o status
        resposta_update = supabase_admin.table("chamadasdevolucao").update(
            {"status": "fechada"}
        ).eq("id_chamada_devolucao", id_devolucao).eq("id_usuario", user["sub"]).execute() # Garante que só o dono feche

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

# --- ENDPOINTS DE LISTAGEM (Consulta) ---

# CORREÇÃO DO ERRO 500: Removido o `response_model` que estava causando o ResponseValidationError
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
        # Retorna os dados brutos do banco (lista)
        return resposta.data

    except Exception as e:
        print(f"Erro ao buscar devoluções no Supabase: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro ao buscar as devoluções."
        )

# --- ENDPOINT DE RELATÓRIO MOVIDO PARA relatorios.py ---
# /alertas

# CORREÇÃO DO ERRO 500: Removido o `response_model`
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
            .select("*, revistas_chamadasdevolucao(*, revistas(nome, numero_edicao))") # Join
            .eq("id_chamada_devolucao", id_devolucao)
            .eq("id_usuario", user["sub"]) # Garantir que o usuário só veja o dele
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
        # O erro "JSON object requested" acontece quando .single() não encontra nada
        if "No rows" in msg or "multiple (or no) rows returned" in msg or "JSON object requested" in msg:
            raise HTTPException(status_code=404, detail=f"Devolução {id_devolucao} não encontrada ou não pertence a este usuário.")
        raise HTTPException(status_code=500, detail=msg)