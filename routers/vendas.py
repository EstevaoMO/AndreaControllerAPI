from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from supabase import Client, create_client

from models.venda_model import VendaFormularioCodBarras, VendaFormularioId

from settings.settings import importar_configs
from services.auth import validar_token, pegar_usuario_admin
# CORREÇÃO: Removida a importação de 'pegar_revistas' que estava causando o TypeError
# from routers.revistas import pegar_revistas

# Configurações iniciais
router = APIRouter(
    prefix="/vendas",
    tags=["Vendas"]
)

st = importar_configs()
supabase: Client = create_client(st.SUPABASE_URL, st.SUPABASE_API_KEY)

def _atualizar_contagem_devolucao(supabase_admin: Client, id_revista_vendida: str, qtd_vendida: int, id_usuario: str):
    """
    Atualiza a contagem de devolução na tabela 'revistas_chamadasdevolucao'
    decrementando 'qtd_a_devolver' com base na venda realizada.
    """
    try:
        # --- CORREÇÃO NA CONSULTA ---
        # 1. Trocamos 'id_revista_chamada' por 'id_chamada_devolucao'
        # 2. Adicionamos a consulta na tabela 'chamadasdevolucao' (via join) para filtrar pelo 'id_usuario'
        chamadas_pendentes = supabase_admin.table("revistas_chamadasdevolucao") \
                    .select("id_chamada_devolucao, qtd_a_devolver") \
                    .eq("id_revista", id_revista_vendida) \
                    .gt("qtd_a_devolver", 0) \
                    .order("data_recebimento", desc=False) \
                    .execute()

        qtd_restante_para_decrementar = qtd_vendida

        for chamada in chamadas_pendentes.data:
            if qtd_restante_para_decrementar <= 0:
                break

            # --- CORREÇÃO NO NOME DA CHAVE ---
            id_chamada_devolucao = chamada["id_chamada_devolucao"]
            qtd_a_devolver_atual = chamada["qtd_a_devolver"]

            if qtd_a_devolver_atual <= qtd_restante_para_decrementar:
                # Decrementa toda a quantidade desta chamada

                # --- CORREÇÃO NO UPDATE (CHAVE COMPOSTA) ---
                # Precisamos filtrar por 'id_chamada_devolucao' E 'id_revista'
                supabase_admin.table("revistas_chamadasdevolucao") \
                    .update({"qtd_a_devolver": 0}) \
                    .eq("id_chamada_devolucao", id_chamada_devolucao) \
                    .eq("id_revista", id_revista_vendida) \
                    .execute()
                qtd_restante_para_decrementar -= qtd_a_devolver_atual
            else:
                # Decrementa apenas o necessário e sai do loop
                nova_qtd_a_devolver = qtd_a_devolver_atual - qtd_restante_para_decrementar

                # --- CORREÇÃO NO UPDATE (CHAVE COMPOSTA) ---
                supabase_admin.table("revistas_chamadasdevolucao") \
                    .update({"qtd_a_devolver": nova_qtd_a_devolver}) \
                    .eq("id_chamada_devolucao", id_chamada_devolucao) \
                    .eq("id_revista", id_revista_vendida) \
                    .execute()
                qtd_restante_para_decrementar = 0

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao atualizar a contagem de devolução: {str(e)}"
        )

@router.get("/tudo")
def pegar_vendas(user = Depends(validar_token)):
    """ Lista todas as vendas (GET básico) """
    try:
        supabase_admin = pegar_usuario_admin()
        dados = supabase_admin.table("vendas").select("id_venda, id_usuario, id_produto, metodo_pagamento, qtd_vendida, desconto_aplicado, valor_total, data_venda").execute()
        return {
            "data": dados.data,
            "message": "Vendas listadas com sucesso."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao acessar o banco de dados: {str(e)}")

# --- ENDPOINTS DE RELATÓRIO MOVIDOS PARA relatorios.py ---
# /recentes
# /hoje
# /relatorio-semana
# /dashboard-geral

@router.post("/cadastrar-venda-por-codigo")
def cadastrar_venda_codigo(venda: VendaFormularioCodBarras, user: dict = Depends(validar_token)):
    """
    Endpoint para persistir uma venda (por CÓDIGO DE BARRAS).
    Esta operação ATUALIZA (decrementa) o estoque E
    ATUALIZA (decrementa) a contagem de devolução ('qtd_a_devolver').
    """

    supabase_admin = pegar_usuario_admin()

    # --- LÓGICA DE BUSCA DA REVISTA (CORRIGIDA) ---
    try:
        # 1. Busca a revista diretamente usando o cliente admin
        resposta_revista = supabase_admin.table("revistas") \
            .select("id_revista, nome, qtd_estoque") \
            .like("codigo_barras", f"{venda.codigo_barras}%") \
            .limit(1) \
            .execute()

        if not resposta_revista.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Revista com esse código de barras não existe no banco de dados."
            )

        revista_encontrada = resposta_revista.data[0]
        id_revista = revista_encontrada["id_revista"]

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Erro ao buscar revista: {str(e)}")
    # --- FIM DA LÓGICA DE BUSCA ---


    # --- ATUALIZAÇÃO DE ESTOQUE (TABELA 'revistas') ---
    estoque_atual = revista_encontrada.get("qtd_estoque", 0)
    qtd_vendida_nesta_transacao = venda.qtd_vendida

    if estoque_atual < qtd_vendida_nesta_transacao:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estoque insuficiente para '{revista_encontrada.get('nome')}'. Estoque atual: {estoque_atual}, Pedido: {qtd_vendida_nesta_transacao}"
        )

    novo_estoque = estoque_atual - qtd_vendida_nesta_transacao

    try:
        supabase_admin.table("revistas").update(
            {"qtd_estoque": novo_estoque}
        ).eq("id_revista", id_revista).execute()

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao atualizar o estoque da revista: {str(e)}"
        )

    # --- REGISTRO DA VENDA (TABELA 'vendas') ---
    dados_venda = {
        "id_usuario": user["sub"],
        "metodo_pagamento": venda.metodo_pagamento,
        "id_produto": id_revista,
        "qtd_vendida": venda.qtd_vendida,
        "desconto_aplicado": venda.desconto_aplicado,
        "valor_total": venda.valor_total,
        "data_venda": venda.data_venda.isoformat()
    }

    resposta_insert = supabase_admin.table("vendas").insert(dados_venda).execute()

    if not resposta_insert.data:
        # Se a inserção da venda falhar, reverter o estoque
        supabase_admin.table("revistas").update(
            {"qtd_estoque": estoque_atual} # Reverte para o estoque antigo
        ).eq("id_revista", id_revista).execute()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao cadastrar a venda no banco (estoque revertido)."
        )

    # --- ATUALIZAÇÃO DA CONTAGEM DE DEVOLUÇÃO (TABELA 'revistas_chamadasdevolucao') ---
    _atualizar_contagem_devolucao(
        supabase_admin=supabase_admin,
        id_revista_vendida=id_revista,
        qtd_vendida=venda.qtd_vendida,
        id_usuario=user["sub"]
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": {"novo_estoque": novo_estoque},
            "message": "Venda cadastrada, estoque e contagem de devolução atualizados!"
        }
    )


@router.post("/cadastrar-venda-por-id")
def cadastrar_venda_id(venda: VendaFormularioId, user: dict = Depends(validar_token)):
    """
    Endpoint para persistir uma venda (por ID DA REVISTA).
    Esta operação ATUALIZA (decrementa) o estoque E
    ATUALIZA (decrementa) a contagem de devolução ('qtd_a_devolver').
    """

    supabase_admin = pegar_usuario_admin()
    revista_encontrada = None

    try:
        resposta_revista = supabase_admin.table("revistas").select(
            "id_revista, nome, qtd_estoque"
        ).eq('id_revista', venda.id_revista).single().execute()

        if not resposta_revista.data:
            raise Exception("Revista não encontrada")

        revista_encontrada = resposta_revista.data
        id_revista = revista_encontrada["id_revista"]

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revista com o id {venda.id_revista} não existe no banco de dados."
        )

    # --- ATUALIZAÇÃO DE ESTOQUE (TABELA 'revistas') ---
    estoque_atual = revista_encontrada.get("qtd_estoque", 0)
    qtd_vendida_nesta_transacao = venda.qtd_vendida

    if estoque_atual < qtd_vendida_nesta_transacao:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estoque insuficiente para '{revista_encontrada.get('nome')}'. Estoque atual: {estoque_atual}, Pedido: {qtd_vendida_nesta_transacao}"
        )

    novo_estoque = estoque_atual - qtd_vendida_nesta_transacao

    try:
        supabase_admin.table("revistas").update(
            {"qtd_estoque": novo_estoque}
        ).eq("id_revista", id_revista).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao atualizar o estoque da revista: {str(e)}"
        )

    # --- REGISTRO DA VENDA (TABELA 'vendas') ---
    dados_venda = {
        "id_usuario": user["sub"],
        "metodo_pagamento": venda.metodo_pagamento,
        "id_produto": id_revista,
        "qtd_vendida": venda.qtd_vendida,
        "desconto_aplicado": venda.desconto_aplicado,
        "valor_total": venda.valor_total,
        "data_venda": venda.data_venda.isoformat()
    }

    resposta_insert = supabase_admin.table("vendas").insert(dados_venda).execute()

    if not resposta_insert.data:
        # Reverte o estoque se a venda falhar
        supabase_admin.table("revistas").update(
            {"qtd_estoque": estoque_atual}
        ).eq("id_revista", id_revista).execute()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao cadastrar a venda no banco (estoque revertido)."
        )

    # --- ATUALIZAÇÃO DA CONTAGEM DE DEVOLUÇÃO (TABELA 'revistas_chamadasdevolucao') ---
    _atualizar_contagem_devolucao(
        supabase_admin=supabase_admin,
        id_revista_vendida=id_revista,
        qtd_vendida=venda.qtd_vendida,
        id_usuario=user["sub"]
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "data": {"novo_estoque": novo_estoque},
            "message": "Venda cadastrada, estoque e contagem de devolução atualizados!"
        }
    )


# =============== RELATÓRIOS (MOVIDOS) ===============