from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from supabase import Client, create_client

from models.venda_model import VendaFormulario

from settings.settings import importar_configs
from services.auth import validar_token, pegar_usuario

# Configurações iniciais
router = APIRouter(
    prefix="/vendas",
    tags=["Vendas"]
)

st = importar_configs()
supabase: Client = create_client(st.SUPABASE_URL, st.SUPABASE_API_KEY)

@router.get("/relatorio")
def pegar_relatorio(user = Depends(validar_token)):
    pass

@router.post("/cadastrar-venda")
def cadastrar_venda(venda: VendaFormulario, user: dict = Depends(validar_token)):
    """
    Endpoint para persistir uma venda no banco do Supabase
    """
    id_revista = supabase.table("revistas").select("id_revista").eq('codigo_barras', venda.codigo_barras).execute().data[0]['id_revista']
    
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