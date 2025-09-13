from fastapi import APIRouter, HTTPException,  Depends
from supabase import Client, create_client

from models.revista_model import Revista

from settings.settings import importar_configs
from services.auth import validar_token

from rapidfuzz import fuzz


# Configurações iniciais
router = APIRouter(
    prefix="/busca",
    tags=["Busca"]
)

st = importar_configs()
supabase: Client = create_client(st.SUPABASE_URL, st.SUPABASE_API_KEY)

@router.get("/nome")
def obter_revistas_por_nome_ou_apelido(q: str, user: str = Depends(validar_token)):
    """
    Endpoint para obter a(s) revista(s) buscada(s) pelo seu nome ou apelido, utilizando fuzzy search para definir a proximidade do parâmetro de busca com o nome no banco de dados.
    """
    
    try:
        dados = supabase.table("Revistas").select("id_revista, nome, apelido_revista, numero_edicao, codigo_barras, qtd_estoque, preco_capa, preco_liquido").execute()
        
        if not dados.data:
            raise HTTPException(status_code=404, detail="Nenhuma revista encontrada no banco de dados.")
 
        revistas = []
        for item in dados.data:
            scores = [
                fuzz.token_sort_ratio(str(q), str(item["nome"])),
                fuzz.token_sort_ratio(str(q), str(item.get("apelido_revista") or ""))
            ]
            max_score = max(scores)
            
            if max_score >= 80:
                revista = Revista(
                    id_revista=item["id_revista"],
                    nome=item["nome"],
                    apelido_revista=item.get("apelido_revista", ""),
                    numero_edicao=item["numero_edicao"],
                    codigo_barras=item["codigo_barras"],
                    qtd_estoque=item["qtd_estoque"],
                    preco_capa=item["preco_capa"],
                    preco_liquido=item["preco_liquido"],
                )
                revistas.append(revista)
        
        if not revistas:
            raise HTTPException(status_code=404, detail="Nenhuma revista encontrada com o nome fornecido.")
        
        return revistas
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao acessar o banco de dados: {str(e)}")