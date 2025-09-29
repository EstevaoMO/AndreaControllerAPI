from pydantic import BaseModel

class RevistaResposta(BaseModel):
    id_revista: int
    nome: str
    apelido_revista: str | None = None
    numero_edicao: str
    codigo_barras: str
    qtd_estoque: int
    preco_capa: float
    preco_liquido: float
    score: float | None = None