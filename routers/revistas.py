from fastapi import APIRouter, HTTPException, status, UploadFile, File, Depends
from supabase import Client, create_client

from models.revista_model import RevistaResposta, CadastrarCodigoRevista

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
    return {
        "data": pegar_revistas().data,
        "message": "Revistas listadas com sucesso."
    }

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

    return {
        "data": revistas,
        "message": "Revistas encontradas com sucesso."
    }

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
            return {
                "data": revista,
                "message": "Revista encontrada com sucesso."
            }

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

    return {
        "data": revistas,
        "message": "Revistas encontradas com sucesso."
    }

@router.post("/cadastrar-foto")
async def upload_image(codigo: str, imagem: UploadFile = File(...), user: dict = Depends(validar_token)):
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
        }).eq('id_revista', codigo).execute()

        return {
            "data": {
                "caminho_bucket": caminho,
                "url": url,
                "database_updated": len(response.data) > 0,
            },
            "message": "Imagem enviada e banco atualizado com sucesso"
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao salvar o arquivo: {e}")

@router.post("/cadastrar-codigo")
def cadastrar_codigo_barras(revista: CadastrarCodigoRevista, user: dict = Depends(validar_token)):
    try:
        if (len(revista.codigo_barras) != 13 or not revista.codigo_barras.isdigit()):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"O código de barras fornecido não tem 13 dígitos ou não é composto apenas por números: {revista.codigo_barras}")

        dados = pegar_revistas()

        if not dados.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Nenhuma revista encontrada no banco de dados.")

        response = None
        for item in dados.data:
            if (item["nome"] == revista.nome and item["numero_edicao"] == revista.numero_edicao):
                if (not item["codigo_barras"] or len(item["codigo_barras"]) != 13):
                    response = supabase.table("revistas").update({
                        'codigo_barras': revista.codigo_barras
                    }).eq('id_revista', item["id_revista"]).execute()

                    break
                else:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Revista {item["nome"]} ({item["numero_edicao"]}) já possui código de barras: {item["codigo_barras"]}")

        if response is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Nenhuma revista encontrada com esse nome e edição. Nome fornecido: {revista.nome};  Edição fornecida: {revista.numero_edicao}"
            )

        return {
            "data": response.data,
            "message": "Código de barras atualizado com sucesso"
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao atualizar revista: {e}")