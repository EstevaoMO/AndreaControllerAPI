from fastapi import APIRouter, UploadFile, HTTPException, File, Depends, status, Query
from datetime import datetime, time, timezone, timedelta
from supabase import Client
from typing import List, Dict, Any, Optional
from datetime import date
import json

from models.chamada_model import ChamadaDevolucaoResposta
from models.alerta_chamada import AlertaChamada
from settings.settings import importar_configs
from services.auth import validar_token, pegar_usuario_admin



router = APIRouter(
    prefix="/chamadas",
    tags=["Chamadas"]
)

st = importar_configs()
URL_EXPIRATION_SECONDS = 30 * 24 * 60 * 60 

def _as_date(value) -> Optional[date]:
    """Converte datetime/ISO/date (como o Supabase pode devolver) para date."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        # tenta ISO completo (com ou sem 'Z')
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except Exception:
            # tenta apenas YYYY-MM-DD
            try:
                return datetime.strptime(value, "%Y-%m-%d").date()
            except Exception:
                return None
    return None

# Permissão de Admin para colocar arquivo no bucket
# Era aqui que estava dando problema, a lógica é que você precisa de permissão de adm para inserir dados em BUCKETs
# Usando a chave "service_key" conseguimos essa permissão, mas inserimos como um usuário diferente do usuário logado
# Por isso, dentro de 'docs', fiz os arquivos serem salvos dentro de uma pasta com o user_id
def _cadastrar_revistas_db(chamada_json: Dict[str, Any], supabase_admin: Client, id_chamada: int) -> int:
    """
    Processa os dados das revistas do JSON e os insere em lote na tabela 'revistas'.
    Retorna a quantidade de revistas inseridas com sucesso.
    """
    revistas_para_inserir = []
    lista_revistas_json = chamada_json.get("revistas", [])

    if not lista_revistas_json:
        return 0

    for revista_data in lista_revistas_json:
        try:
            preco_capa_str = str(revista_data.get("pco_capa", "0.0")).replace(',', '.')
            preco_liq_str = str(revista_data.get("pco_liq", "0.0")).replace(',', '.')
            
            revistas_para_inserir.append({
                "nome": revista_data.get("produto"),
                "apelido_revista": revista_data.get("subtitulo"),
                "numero_edicao": int(revista_data.get("edicao", 0)),
                "codigo_barras": str(revista_data.get("ean", "")).strip(),
                "qtd_estoque": int(revista_data.get("rep") or 0),
                "preco_capa": float(preco_capa_str),
                "preco_liquido": float(preco_liq_str),
            })
        except (ValueError, TypeError) as e:
            print(f"Aviso: Ignorando revista com dados inválidos: {revista_data.get('produto')}. Erro: {e}")
            continue

    if not revistas_para_inserir:
        return 0

    try:
        resposta_revistas = supabase_admin.table("revistas").insert(revistas_para_inserir).execute()
        return len(resposta_revistas.data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ocorreu um erro de banco de dados ao inserir as revistas: {e}"
        )


@router.post("/cadastrar-chamada", status_code=status.HTTP_201_CREATED)
async def cadastrar_chamada(file: UploadFile = File(...), user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)):
    """
    Recebe um ARQUIVO JSON, salva-o no storage, interpreta seu conteúdo
    e insere os dados da chamada e das revistas no banco.
    """
    arquivo_bytes = await file.read()
    if not arquivo_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O arquivo enviado está vazio.")
    
    try:
        chamada_json = json.loads(arquivo_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O arquivo enviado não contém um JSON válido.")

    if "chamada_encalhe" not in chamada_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O conteúdo do JSON é inválido. A chave 'chamada_encalhe' é obrigatória."
        )


    # Carrega o arquivo json no Bucket, criando uma pasta com o user_id
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    caminho_arquivo = f"{user['sub']}/{timestamp}_{file.filename}"
    try:
        supabase_admin.storage.from_(st.BUCKET).upload(
            path=caminho_arquivo,
            file=arquivo_bytes,
            file_options={"content-type": file.content_type or "application/json"}
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao salvar o arquivo: {e}")

    try:
        assinatura = supabase_admin.storage.from_(st.BUCKET).create_signed_url(caminho_arquivo, URL_EXPIRATION_SECONDS)
        url_assinada = assinatura.get("signedURL")
        if not url_assinada:
            raise ValueError("A resposta da URL assinada não contém a chave 'signedURL'.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao gerar URL para o documento: {e}")
    
    try:
        dados_chamada = {
            "id_usuario": user["sub"],
            "ponto_venda_id": chamada_json["chamada_encalhe"]["ponto"],
            "data_limite": datetime.strptime(chamada_json["chamada_encalhe"]["data_da_chamada"], "%d/%m/%Y").strftime("%Y-%m-%d"),
            "url_documento": url_assinada,
            "status": "aberta"
        }
        resposta_insert = supabase_admin.table("chamadasdevolucao").insert(dados_chamada).execute()
        chamada_criada = resposta_insert.data[0]
        id_chamada_criada = chamada_criada['id_chamada_devolucao']
    except (KeyError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A estrutura do JSON dentro do arquivo está incorreta.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao registrar a chamada no banco de dados: {e}")


    # AQUI ELE CADASTRA AS REVISTAS
    revistas_inseridas = _cadastrar_revistas_db(chamada_json, supabase_admin, id_chamada_criada)
    
    return {
        "mensagem": "Chamada criada e revistas cadastradas com sucesso.",
        "id_chamada": id_chamada_criada,
        "url_documento": url_assinada,
        "qtd_revistas_cadastradas": revistas_inseridas
    }

@router.get("/listar-chamadas-usuario")
async def listar_chamadas_por_usuario(user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)) -> List[ChamadaDevolucaoResposta]:
    """
    Lista todas as chamadas de devolução associadas ao usuário autenticado.
    """
    try:
        resposta = (
            supabase_admin.table("chamadasdevolucao")
            .select("*")
            .eq("id_usuario", user["sub"])
            .order("data_limite", desc=True)
            .execute()
        )
        return resposta.data
    except Exception as e:
        print(f"Erro ao buscar chamadas no Supabase: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro ao buscar as chamadas de devolução."
        )

@router.get("/alertas",response_model=List[AlertaChamada],summary="Alertas de chamadas com data_limite em ≤ N dias")
async def listar_alertas_chamadas(
    dias: int = Query(5, ge=0, le=60, description="Janela a partir de hoje (padrão=5)"),
    incluir_vencidas: bool = Query(
        True, description="Se True, inclui itens já vencidos (ex.: venceu no sábado, avisa na segunda)."
    ),
    user: dict = Depends(validar_token),
    supabase_admin: Client = Depends(pegar_usuario_admin),
):
    """
    Regra:
    - incluir_vencidas=True  -> traz tudo com data_limite <= hoje+N (inclui atrasadas)
    - incluir_vencidas=False -> apenas hoje <= data_limite <= hoje+N
    Sempre filtrando pelo usuário autenticado.
    """
    hoje = date.today()
    limite = hoje + timedelta(days=dias)
    today_str = hoje.strftime("%Y-%m-%d")
    limit_str = limite.strftime("%Y-%m-%d")

    try:
        q = (
            supabase_admin
            .table("chamadasdevolucao")
            .select("id_chamada_devolucao,data_limite,status")
        )

        if incluir_vencidas:
            # Compatível com coluna DATE
            q = q.lte("data_limite", limit_str)
        else:
            q = q.gte("data_limite", today_str).lte("data_limite", limit_str)

        q = q.order("data_limite", desc=False)
        resp = q.execute()
        rows = resp.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar Supabase: {e!s}")

    saida: List[AlertaChamada] = []

    for r in rows:
        enc = _as_date(r.get("data_limite"))
        if enc is None:
            continue

        # Guarda de segurança (se o PostgREST devolver algo fora do range por TZ)
        if incluir_vencidas:
            if enc > limite:
                continue
        else:
            if enc < hoje or enc > limite:
                continue

        dias_restantes = (enc - hoje).days

        saida.append(
            AlertaChamada(
                id=int(r["id_chamada_devolucao"]),  # ajuste se sua PK não for 'id'
                data_limite=enc,
                dias_restantes=dias_restantes,
                status=r.get("status", "")
            )
        )

    return saida

@router.get("/{id}", response_model=ChamadaDevolucaoResposta)
async def get_chamada_por_id(id: int, user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)) -> ChamadaDevolucaoResposta:
    """
    Retorna os dados de uma chamada de devolução pelo ID.
    """
    try:
        resposta = (
            supabase_admin.table("chamadasdevolucao")
            .select("*")
            .eq("id_chamada_devolucao", id)
            .single()
            .execute()
        )

        if not resposta.data:
            raise HTTPException(status_code=404, detail=f"Chamada {id} não encontrada")

        return resposta.data

    except Exception as e:
        msg = str(e)
        if "No rows" in msg or "multiple (or no) rows returned" in msg:
            raise HTTPException(status_code=404, detail=f"Chamada {id} não encontrada")
        raise HTTPException(status_code=500, detail=msg)
    
