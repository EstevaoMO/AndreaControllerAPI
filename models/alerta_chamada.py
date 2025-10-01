# models/alerta_chamada.py
from pydantic import BaseModel
from datetime import date

class AlertaChamada(BaseModel):
    id: int
    data_limite: date
    dias_restantes: int
    status: str