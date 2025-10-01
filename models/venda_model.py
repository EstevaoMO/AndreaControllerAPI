from pydantic import BaseModel
from enum import Enum
from datetime import datetime

class MetodoPagamentoEnum(str, Enum):
    debito = "Débito"
    credito = "Crédito"
    dinheiro = "Dinheiro"
    pix = "Pix"

class VendaFormularioCodBarras(BaseModel):
    metodo_pagamento: MetodoPagamentoEnum
    codigo_barras: str
    qtd_vendida: int
    desconto_aplicado: float
    valor_total: float
    data_venda: datetime

class VendaFormularioId(BaseModel):
    id_revista: int
    metodo_pagamento: MetodoPagamentoEnum
    qtd_vendida: int
    desconto_aplicado: float
    valor_total: float
    data_venda: datetime