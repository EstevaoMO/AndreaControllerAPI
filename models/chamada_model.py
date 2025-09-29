from pydantic import BaseModel
from datetime import datetime

class ChamadaDevolucaoResposta(BaseModel):
    id: int
    id_usuario: int
    ponto_venda_id: int
    data_limite: datetime
    url_documento: str
    status: str