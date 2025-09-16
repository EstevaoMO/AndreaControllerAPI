# models/chamada.py
from pydantic import BaseModel
from datetime import date
from typing import Optional

class Chamada(BaseModel):
    id: int  # troque para str se a tabela usar UUID
    id_usuario: str
    ponto_venda_id: str
    data_limite: date
    url_documento: str
    status: str
    created_at: Optional[date] = None

    class Config:
        from_attributes = True  # compatível com dict/ORM-like
