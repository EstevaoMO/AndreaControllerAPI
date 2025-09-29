from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from supabase import Client, create_client

from models.venda_model import VendaFormularioCodBarras, VendaFormularioId

from settings.settings import importar_configs
from services.auth import validar_token, pegar_usuario
from routers.revistas import pegar_revistas

# Configurações iniciais
router = APIRouter(
    prefix="/vendas",
    tags=["Vendas"]
)

st = importar_configs()
supabase: Client = create_client(st.SUPABASE_URL, st.SUPABASE_API_KEY)

@router.get("/tudo")
def pegar_vendas(user = Depends(validar_token)):
    try:
        dados = supabase.table("vendas").select("id_venda, id_usuario, id_produto, metodo_pagamento, qtd_vendida, desconto_aplicado, valor_total, data_venda").execute()
        return dados.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao acessar o banco de dados: {str(e)}")

@router.get("/recentes")
def pegar_relatorio_dia(user = Depends(validar_token)):
    try:
        recentes = supabase.table("vw_vendas_recentes").select("*").execute()
        return recentes.data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"    
        )

@router.post("/cadastrar-venda-por-codigo")
def cadastrar_venda_codigo(venda: VendaFormularioCodBarras, user: dict = Depends(validar_token)):
    """
    Endpoint para persistir uma venda no banco do Supabase
    """

    revistas = pegar_revistas().data
    if not revistas:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Nenhuma revista encontrada no banco de dados.")
    
    id_revista = -1
    for item in revistas:
        if item["codigo_barras"][0:13] == str(venda.codigo_barras):
            id_revista  = item["id_revista"]
            break
    if id_revista == -1:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Revista com esse código de barras não existe no banco de dados."
        )
        

    dados_venda = {
        "id_usuario": user["sub"],
        "metodo_pagamento": venda.metodo_pagamento,
        "id_produto": id_revista,
        "qtd_vendida": venda.qtd_vendida,
        "desconto_aplicado": venda.desconto_aplicado,
        "valor_total": venda.valor_total,
        "data_venda": venda.data_venda.isoformat() # Tratar data para o formato usado no banco
    }

    # Inserir linha no banco
    resposta_insert = supabase.table("vendas").insert(dados_venda).execute()

    if resposta_insert.data:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"mensagem": "Venda cadastrada com sucesso!"}
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao cadastrar a venda no banco."
        )
    
@router.post("/cadastrar-venda-por-id")
def cadastrar_venda_id(venda: VendaFormularioId, user: dict = Depends(validar_token)):
    """
    Endpoint para persistir uma venda no banco do Supabase
    """

    try:
        id_revista = supabase.table("revistas").select("id_revista").eq('id_revista', venda.id_revista).execute().data[0]['id_revista']
    except:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Revista com esse id não existe no banco de dados."
        )

    dados_venda = {
        "id_usuario": user["sub"],
        "metodo_pagamento": venda.metodo_pagamento,
        "id_produto": id_revista,
        "qtd_vendida": venda.qtd_vendida,
        "desconto_aplicado": venda.desconto_aplicado,
        "valor_total": venda.valor_total,
        "data_venda": venda.data_venda.isoformat() # Tratar data para o formato usado no banco
    }

    # Inserir linha no banco
    resposta_insert = supabase.table("vendas").insert(dados_venda).execute()

    if resposta_insert.data:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"mensagem": "Venda cadastrada com sucesso!"}
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao cadastrar a venda no banco."
        )


# =============== RELTARÓIOS ===============
@router.get("/relatorio-dia")
def pegar_relatorio_dia(user = Depends(validar_token)):
    try:
        vendas_hoje = supabase.table("vw_vendas_hoje").select("*").execute()
        return vendas_hoje.data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"    
        )

@router.get("/relatorio-semana")
def pegar_relatorio_semana(user = Depends(validar_token)):
    try:
        vendas_hoje = supabase.table("mv_performance_semanal").select("*").execute()
        return vendas_hoje.data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"    
        )

@router.get("/relatorio-semana")
def pegar_relatorio_dia(user = Depends(validar_token)):
    try:
        vendas_semana = supabase.table("mv_performance_semanal").select("*").execute()
        return vendas_semana.data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Algo de errado aconteceu: {str(e)}"    
        )