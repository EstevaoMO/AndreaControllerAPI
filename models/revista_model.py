from pydantic import BaseModel

# Modelo de revista para resposta dos endpoints que retornam revistas
class RevistaResposta(BaseModel):
    id_revista: int
    nome: str
    apelido_revista: str | None = None
    numero_edicao: int
    codigo_barras: str
    qtd_estoque: int
    preco_capa: float
    preco_liquido: float | None = None
    score: float | None = None

# Modelo de body para receber uma revista no endpoint de cadastrar código de barras
class CadastrarCodigoRevista(BaseModel):
    nome: str
    numero_edicao: int
    codigo_barras: str