from fastapi import APIRouter, HTTPException, status, UploadFile, File, Depends
from supabase import Client, create_client

from models.revista_model import RevistaResposta

from settings.settings import importar_configs
from services.auth import validar_token

from rapidfuzz import fuzz

# Configurações iniciais
router = APIRouter(
    prefix="/revistas",
    tags=["Revistas"]
)

st = importar_configs()
supabase: Client = create_client(st.SUPABASE_URL, st.SUPABASE_API_KEY)

def pegar_revistas():
    try:
        # Coleta todas as revistas do banco de dados
        dados = supabase.table("revistas").select("id_revista, nome, apelido_revista, numero_edicao, codigo_barras, qtd_estoque, preco_capa, preco_liquido").execute()
        return dados
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao acessar o banco de dados: {str(e)}")

@router.get("/tudo")
def pegar_tudo(user = Depends(validar_token)):
    return pegar_revistas().data

@router.get("/buscar/nome")
def obter_revistas_por_nome_ou_apelido(q: str, user: dict = Depends(validar_token)):
    """
    Endpoint para obter a(s) revista(s) buscada(s) pelo seu nome ou apelido, utilizando fuzzy search para definir a proximidade do parâmetro de busca com o nome no banco de dados.
    """
    
    dados = pegar_revistas()
        
    if not dados.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Nenhuma revista encontrada no banco de dados.")

    revistas = []
    for item in dados.data:
        # Cálculo da similaridade usando RapidFuzz, usando .lower e .strip para melhorar a correspondência
        scores = [
            fuzz.token_sort_ratio(str(q).lower().strip(), str(item["nome"]).lower().strip()),
            fuzz.token_sort_ratio(str(q).lower().strip(), str(item.get("apelido_revista") or "").lower().strip())
        ]

        # Já que nome e apelido são considerados ao mesmo tempo, pega apenas o maior valor de similaridade
        max_score = max(scores)
        
        if max_score >= 70:
            # Considera uma correspondência válida se a similaridade for 70 ou mais e adiciona a revista na lista de resultados
            revista = RevistaResposta(
                id_revista=item["id_revista"],
                nome=item["nome"],
                apelido_revista=item.get("apelido_revista", ""),
                numero_edicao=item["numero_edicao"],
                codigo_barras=item["codigo_barras"],
                qtd_estoque=item["qtd_estoque"],
                preco_capa=item["preco_capa"],
                preco_liquido=item["preco_liquido"],
                score=max_score
            )
            revistas.append(revista)
    
    if not revistas:
        raise HTTPException(status_code=404, detail="Nenhuma revista encontrada com o nome fornecido.")
    
    return revistas

@router.get("/buscar/codigo-barras")
def obter_revista_por_codigo_barras(q: str, user: dict = Depends(validar_token)):
    """
    Endpoint para obter a revista buscada pelo seu código de barras.
    """
    
    dados = pegar_revistas()
        
    if not dados.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Nenhuma revista encontrada no banco de dados.")

    for item in dados.data:
        # Busca exata pelo código de barras, removendo espaços em branco com .strip
        if str(item["codigo_barras"]).strip() == str(q).strip():
            revista = RevistaResposta(
                id_revista=item["id_revista"],
                nome=item["nome"],
                apelido_revista=item.get("apelido_revista", ""),
                numero_edicao=item["numero_edicao"],
                codigo_barras=item["codigo_barras"],
                qtd_estoque=item["qtd_estoque"],
                preco_capa=item["preco_capa"],
                preco_liquido=item["preco_liquido"]
            )
            return revista
    
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Nenhuma revista encontrada com o código de barras fornecido.")

@router.get("/buscar/edicao")
def obter_revista_por_edicao(q: str, user: dict = Depends(validar_token)):
    """
    Endpoint para obter a revista buscada pelo seu número de edição.
    """
    
    dados = pegar_revistas()
        
    if not dados.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Nenhuma revista encontrada no banco de dados.")

    revistas = []
    for item in dados.data:
        # Busca exata pelo número de edição, removendo espaços em branco com .strip
        if str(item["numero_edicao"]).strip() == str(q).strip():
            revista = RevistaResposta(
                id_revista=item["id_revista"],
                nome=item["nome"],
                apelido_revista=item.get("apelido_revista", ""),
                numero_edicao=item["numero_edicao"],
                codigo_barras=item["codigo_barras"],
                qtd_estoque=item["qtd_estoque"],
                preco_capa=item["preco_capa"],
                preco_liquido=item["preco_liquido"]
            )
            revistas.append(revista) # Como mais de uma revista pode ter a mesma edição, adiciona na lista
    
    if not revistas:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Nenhuma revista encontrada com o número de edição fornecido.")
    
    return revistas

@router.post("/cadastrar-foto")
async def upload_image(codigo: int, imagem: UploadFile = File(...), user: dict = Depends(validar_token)):
    # Crie um nome pardonizado para a imagem
    extensao = imagem.filename.split('.')[-1] if '.' in imagem.filename else 'jpg'
    caminho = f"img_{codigo}.{extensao}"
    file_bytes = await imagem.read()
    
    try:
        supabase.storage.from_(st.BUCKET_REVISTAS).upload(
            path=caminho, 
            file=file_bytes,
            file_options={"content-type": imagem.content_type or "image/jpeg"})
        url = supabase.storage.from_(st.BUCKET_REVISTAS).get_public_url(caminho)

        # Atualizar a URL na tabela
        response = supabase.table("revistas").update({
            'url_revista': url
        }).eq('codigo_barras', codigo).execute()
        
        return {
            "caminho_bucket": caminho,
            "url": url,
            "database_updated": len(response.data) > 0,
            "message": "Imagem enviada e banco atualizado com sucesso"
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao salvar o arquivo: {e}")