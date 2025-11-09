from fastapi import APIRouter, Depends, HTTPException, status, Query
from supabase import Client
from datetime import date, timedelta

from services.auth import validar_token, pegar_usuario_admin

router = APIRouter(
    prefix="/relatorios",
    tags=["Relatórios"]
)

@router.get("/vendas/dashboard-geral")
def pegar_dashboard_geral(user = Depends(validar_token)):
    """
    Endpoint consolidado para os relatórios da tela principal.
    Estrutura: {hoje:{...}, semana:[...], ticket_medio:valor, mais_vendidos:{...}}
    """
    try:
        supabase_admin = pegar_usuario_admin()

        vendas_hoje_data = supabase_admin.table("vw_vendas_hoje").select("*").execute().data
        vendas_semana_data = supabase_admin.table("mv_performance_semanal").select("*").execute().data
        ranking_data = supabase_admin.table("vw_vendas_recentes").select("*").execute().data

        total_faturado_hoje = 0
        total_vendas_hoje = 0
        if vendas_hoje_data:
            for venda in vendas_hoje_data:
                total_faturado_hoje += venda.get("valor_total", 0)
            total_vendas_hoje = len(vendas_hoje_data)

        dados_hoje_agregado = {
            "faturamento_hoje": total_faturado_hoje,
            "vendas_hoje": total_vendas_hoje
        }

        semana_formatado = vendas_semana_data

        ticket_medio = 0
        if total_vendas_hoje > 0:
            ticket_medio = total_faturado_hoje / total_vendas_hoje

        mais_vendidos_agregado = {}
        if ranking_data:
            for item in ranking_data:
                nome_revista = (
                    item.get("nome") or
                    item.get("revista") or
                    item.get("nome_revista") or
                    item.get("produto") or
                    "Produto Desconhecido"
                )

                qtd = item.get("qtd_vendida", 1)
                mais_vendidos_agregado[nome_revista] = mais_vendidos_agregado.get(nome_revista, 0) + qtd

        sorted_ranking = sorted(mais_vendidos_agregado.items(), key=lambda x: x[1], reverse=True)
        mais_vendidos_formatado = dict(sorted_ranking[:10])

        dashboard_data = {
            "hoje": dados_hoje_agregado,
            "semana": semana_formatado,
            "ticket_medio": ticket_medio,
            "mais_vendidos": mais_vendidos_formatado
        }

        return {
            "data": dashboard_data,
            "message": "Dashboard geral gerado com sucesso."
        }
    except Exception as e:
        detail_message = f"Algo de errado aconteceu ao gerar o dashboard: {str(e)}"
        print(f"ERRO NO DASHBOARD: {detail_message}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail_message
        )


@router.get("/vendas/hoje")
def pegar_hoje(user = Depends(validar_token)):
    """
    Relatório de vendas de hoje (vw_vendas_hoje)
    """
    try:
        supabase_admin = pegar_usuario_admin()

        vendas_hoje_data = supabase_admin.table("vw_vendas_hoje").select("*").execute().data

        faturamento_do_dia = 0
        if vendas_hoje_data:
            for venda in vendas_hoje_data:
                faturamento_do_dia += venda.get("valor_total", 0)

        dados_hoje = {
            "faturamento_do_dia": faturamento_do_dia,
            "ultimas_vendas": vendas_hoje_data
        }

        return {
            "data": dados_hoje,
            "message": "Relatório de hoje gerado com sucesso."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )

@router.get("/kpi/faturamento-hoje")
def pegar_faturamento_hoje(user = Depends(validar_token)):
    """
    KPI: Faturamento do dia atual (vw_kpi_faturamento_hoje)
    """
    try:
        supabase_admin = pegar_usuario_admin()
        
        resultado = supabase_admin.table("vw_kpi_faturamento_hoje").select("*").execute().data
        
        faturamento = 0
        if resultado and len(resultado) > 0:
            faturamento = resultado[0].get("faturamento_hoje", 0)
        
        return {
            "data": {
                "faturamento_hoje": faturamento
            },
            "message": "Faturamento de hoje obtido com sucesso."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )


@router.get("/kpi/unidades-hoje")
def pegar_unidades_hoje(user = Depends(validar_token)):
    """
    KPI: Unidades vendidas no dia atual (vw_kpi_unidades_hoje)
    """
    try:
        supabase_admin = pegar_usuario_admin()
        
        resultado = supabase_admin.table("vw_kpi_unidades_hoje").select("*").execute().data
        
        unidades = 0
        if resultado and len(resultado) > 0:
            unidades = resultado[0].get("unidades_vendidas_hoje", 0)
        
        return {
            "data": {
                "unidades_vendidas_hoje": unidades
            },
            "message": "Unidades vendidas hoje obtidas com sucesso."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )


@router.get("/kpi/devolucoes-pendentes")
def pegar_devolucoes_pendentes(user = Depends(validar_token)):
    """
    KPI: Quantidade de devoluções pendentes (vw_kpi_devolucoes_pendentes)
    """
    try:
        supabase_admin = pegar_usuario_admin()
        
        resultado = supabase_admin.table("vw_kpi_devolucoes_pendentes").select("*").execute().data
        
        devolucoes = 0
        if resultado and len(resultado) > 0:
            devolucoes = resultado[0].get("devolucoes_pendentes", 0)
        
        return {
            "data": {
                "devolucoes_pendentes": devolucoes
            },
            "message": "Devoluções pendentes obtidas com sucesso."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )


@router.get("/kpi/proxima-devolucao")
def pegar_proxima_devolucao(user = Depends(validar_token)):
    """
    KPI: Próxima data limite de devolução (vw_kpi_proxima_devolucao)
    """
    try:
        supabase_admin = pegar_usuario_admin()
        
        resultado = supabase_admin.table("vw_kpi_proxima_devolucao").select("*").execute().data
        
        proxima_data = None
        if resultado and len(resultado) > 0:
            proxima_data = resultado[0].get("proxima_data_limite")
        
        return {
            "data": {
                "proxima_data_limite": proxima_data
            },
            "message": "Próxima data limite de devolução obtida com sucesso."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )


@router.get("/kpi/faturamento-30d")
def pegar_faturamento_30d(user = Depends(validar_token)):
    """
    KPI: Faturamento dos últimos 30 dias (vw_kpi_faturamento_30d)
    """
    try:
        supabase_admin = pegar_usuario_admin()
        
        resultado = supabase_admin.table("vw_kpi_faturamento_30d").select("*").execute().data
        
        faturamento = 0
        if resultado and len(resultado) > 0:
            faturamento = resultado[0].get("faturamento_ultimos_30_dias", 0)
        
        return {
            "data": {
                "faturamento_ultimos_30_dias": faturamento
            },
            "message": "Faturamento dos últimos 30 dias obtido com sucesso."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )


@router.get("/kpi/ticket-medio-30d")
def pegar_ticket_medio_30d(user = Depends(validar_token)):
    """
    KPI: Ticket médio dos últimos 30 dias (vw_kpi_ticket_medio_30d)
    """
    try:
        supabase_admin = pegar_usuario_admin()
        
        resultado = supabase_admin.table("vw_kpi_ticket_medio_30d").select("*").execute().data
        
        ticket_medio = 0
        if resultado and len(resultado) > 0:
            ticket_medio = resultado[0].get("ticket_medio_ultimos_30_dias", 0)
        
        return {
            "data": {
                "ticket_medio_ultimos_30_dias": ticket_medio
            },
            "message": "Ticket médio dos últimos 30 dias obtido com sucesso."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )


# ==================== ENDPOINTS PARA GRÁFICOS ====================

@router.get("/grafico/top5-revistas-hoje")
def pegar_top5_revistas_hoje(user = Depends(validar_token)):
    """
    Gráfico: Top 5 revistas mais vendidas hoje (vw_chart_top5_vendidas_hoje)
    Recomendado: Gráfico de Barras Horizontais
    """
    try:
        supabase_admin = pegar_usuario_admin()
        
        resultado = supabase_admin.table("vw_chart_top5_vendidas_hoje").select("*").execute().data
        
        return {
            "data": resultado if resultado else [],
            "message": "Top 5 revistas vendidas hoje obtido com sucesso."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )

@router.get("/grafico/top5-revistas-7d")
def pegar_top5_revistas_hoje(user = Depends(validar_token)):
    """
    Gráfico: Top 5 revistas mais vendidas nos últimos 7 dias (vw_chart_top5_vendidas_7d)
    Recomendado: Gráfico de Barras Horizontais
    """
    try:
        supabase_admin = pegar_usuario_admin()
        
        resultado = supabase_admin.table("vw_chart_top5_vendidas_7d").select("*").execute().data
        
        return {
            "data": resultado if resultado else [],
            "message": "Top 5 revistas vendidas nos últimos 7 dias obtido com sucesso."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )

@router.get("/grafico/vendas-por-pagamento-30d")
def pegar_vendas_por_pagamento_30d(user = Depends(validar_token)):
    """
    Gráfico: Vendas por método de pagamento (últimos 30 dias) (vw_chart_vendas_por_pagamento_30d)
    Recomendado: Gráfico de Pizza/Rosca
    """
    try:
        supabase_admin = pegar_usuario_admin()
        
        resultado = supabase_admin.table("vw_chart_vendas_por_pagamento_30d").select("*").execute().data
        
        return {
            "data": resultado if resultado else [],
            "message": "Vendas por método de pagamento dos últimos 30 dias obtidas com sucesso."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )


# -----------------------------------------------------------------------------
# Relatórios não sendo usados!!!
# -----------------------------------------------------------------------------


#@router.get("/vendas/semana")
def pegar_relatorio_semana(user = Depends(validar_token)):
    """ Relatório semanal de vendas (mv_performance_semanal). """
    try:
        supabase_admin = pegar_usuario_admin()
        vendas_semana = supabase_admin.table("mv_performance_semanal").select("*").execute()
        return {
            "data": vendas_semana.data,
            "message": "Relatório semanal de vendas gerado com sucesso."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"
        )


#@router.get("/devolucoes/alertas", summary="Alertas de devoluções com data_limite em ≤ N dias")
async def listar_alertas_devolucoes(
    dias: int = Query(5, ge=0, le=60, description="Janela a partir de hoje (padrão=5)"),
    incluir_vencidas: bool = Query(
        True, description="Se True, inclui itens já vencidos."
    ),
    user: dict = Depends(validar_token),
    supabase_admin: Client = Depends(pegar_usuario_admin),
):
    """
    Lista devoluções 'abertas' do usuário que vencem em N dias ou já venceram.
    """
    hoje = date.today()
    limite = hoje + timedelta(days=dias)
    today_str = hoje.strftime("%Y-%m-%d")
    limit_str = limite.strftime("%Y-%m-%d")

    try:
        q = (
            supabase_admin
            .table("chamadasdevolucao")
            .select("id_chamada_devolucao,data_limite,status")
            .eq("id_usuario", user["sub"])
            .eq("status", "aberta")
        )

        if incluir_vencidas:
            q = q.lte("data_limite", limit_str)
        else:
            q = q.gte("data_limite", today_str).lte("data_limite", limit_str)

        q = q.order("data_limite", desc=False)
        resp = q.execute()
        rows = resp.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar Supabase: {e!s}")

    saida = []

    for r in rows:
        data_limite_str = r.get("data_limite")
        if data_limite_str is None:
            continue

        enc = date.fromisoformat(data_limite_str)
        dias_restantes = (enc - hoje).days

        saida.append(
            {
                "id": int(r["id_chamada_devolucao"]),
                "data_limite": enc,
                "dias_restantes": dias_restantes,
                "status": r.get("status", "")
            }
        )

    return saida

#@router.get("/vendas/recentes")
def pegar_relatorio_dia(user = Depends(validar_token)):
    """ Relatório de vendas recentes (vw_vendas_recentes). """
    try:
        supabase_admin = pegar_usuario_admin()
        recentes = supabase_admin.table("vw_vendas_recentes").select("*").execute()
        return {
            "data": recentes.data,
            "message": "Relatório de vendas recentes gerado com sucesso."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,  
        )