from pydantic import BaseModel
from enum import Enum
from datetime import datetime

class MetodoPagamentoEnum(str, Enum):
    debito = "Débito"
    credito = "Crédito"
    dinheiro = "Dinheiro"
    pix = "Pix"

class RelatorioVendasHoje(BaseModel):
    nome: str
    numero_edicao: int
    metodo_pagamento: MetodoPagamentoEnum
    qtd_vendida: int
    desconto_aplicado: float
    valor_total: float
    url_revista: str

class RelatorioVendasRecentes(BaseModel):
    id_venda: int
    revista: str # mesmo que nome
    numero_edicao: int
    qtd_vendida: int
    valor_total: float
    metodo_pagamento: MetodoPagamentoEnum
    data_venda: datetime

class RelatorioRevistasEstoque(BaseModel):
    id_revista: int
    nome: str
    numero_edicao: int
    codigo_barras: str | None = None
    qtd_estoque: int
    preco_capa: float
    preco_liquido: float | None = None

class RelatorioDevolucao(BaseModel):
    pass

class RelatorioEncalheRevista(BaseModel):
    pass