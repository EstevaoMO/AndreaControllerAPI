from pydantic import BaseModel, Field, ConfigDict
from datetime import date

class ChamadaDevolucaoResposta(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(alias="id_chamada_devolucao")

    id_usuario: str          
    ponto_venda_id: str      
    data_limite: date        
    url_documento: str
    status: str
