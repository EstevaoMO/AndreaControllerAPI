from fastapi import APIRouter, UploadFile, HTTPException, File, Depends, status, Query
from datetime import datetime, date, timedelta
from supabase import Client
from typing import List, Dict, Any
import json

from models.chamada_model import ChamadaDevolucaoResposta, AlertaChamadaNotificacao
from settings.settings import importar_configs
from services.auth import validar_token, pegar_usuario_admin
from services.extracao import processar_pdf_para_json
from routers.revistas import pegar_revistas


router = APIRouter(
    prefix="/chamadas",
    tags=["Chamadas"]
)

st = importar_configs()

# Permissão de Admin para colocar arquivo no bucket
# Era aqui que estava dando problema, a lógica é que você precisa de permissão de adm para inserir dados em BUCKETs
# Usando a chave "service_key" conseguimos essa permissão, mas inserimos como um usuário diferente do usuário logado
# Por isso, dentro de 'docs', fiz os arquivos serem salvos dentro de uma pasta com o user_id
def _cadastrar_revistas_db(chamada_json: Dict[str, Any], supabase_admin: Client, id_chamada: str) -> tuple[int, int, int]:
    """
    Processa os dados das revistas do JSON e os insere em lote na tabela 'revistas'.
    Retorna a quantidade de revistas inseridas com sucesso.
    """
    lista_revistas_json = chamada_json.get("revistas", [])

    if not lista_revistas_json:
        return (0, 0)

    revistas_banco = pegar_revistas()
    revistas_existentes = revistas_banco.data if revistas_banco and revistas_banco.data else []

    inseridas = 0
    atualizadas = 0
    inseridas_relacionamento = 0
    
    def inserir_revista(revista):
        try:
            resposta_insert = supabase_admin.table("revistas").insert({
                "nome": revista["nome"],
                "numero_edicao": revista["numero_edicao"],
                "codigo_barras": revista["codigo_barras"],
                "qtd_estoque": revista["qtd_estoque"],
                "preco_capa": revista["preco_capa"],
                "preco_liquido": revista["preco_liquido"]
            }).execute()

            revista_criada = resposta_insert.data[0]
            return revista_criada
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao inserir revista: {e}; Revista: {revista}")

    def atualizar_codigo_barras(id_revista, revista):
        try:
            supabase_admin.table("revistas").update({
                'codigo_barras': revista["codigo_barras"]
            }).eq('id_revista', id_revista).execute()
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao atualizar revista: {e}; ID da revista: {id_revista}; Revista: {revista}")

    def inserir_relacao_chamada(id_revista, revista):
        try:
            supabase_admin.table("revistas_chamadasdevolucao").insert({
                "id_chamada_devolucao": id_chamada,
                "id_revista": id_revista,
                "data_recebimento": revista["data_entrega"],
                "qtd_recebida": revista["qtd_estoque"],
            }).execute()
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao inserir relação entre revista e chamada: {e}; ID da revista: {id_revista}; Revista: {revista}")

    for revista in lista_revistas_json:
        try:
            revista["codigo_barras"] = str(revista["codigo_barras"])[:13]
            if (len(str(revista["codigo_barras"])) != 13 or not revista["codigo_barras"].isdigit()):
                raise ValueError(f"O código de barras fornecido não tem 13 dígitos ou não é composto apenas por números: {revista}")
            achou = False
            for item in revistas_existentes:
                if item["codigo_barras"] is not None and (item["codigo_barras"] == revista["codigo_barras"]):
                    inserir_relacao_chamada(item["id_revista"], revista)
                    inseridas_relacionamento += 1
                    achou = True
                    break

                if (item["nome"] == revista["nome"] and item["numero_edicao"] == revista["numero_edicao"]):
                    if (not item["codigo_barras"] or len(str(item["codigo_barras"])) != 13):
                        atualizar_codigo_barras(item["id_revista"], revista)
                        inserir_relacao_chamada(item["id_revista"], revista)
                        atualizadas += 1
                        inseridas_relacionamento += 1
                        achou = True
                        break
                    else:
                        raise ValueError(f"Revista {item['nome']} ({item['numero_edicao']}) já possui código de barras: {item['codigo_barras']}; Revista do banco: {item}; Revista do JSON: {revista}")
            if not achou:
                nova_revista = inserir_revista(revista)
                inserir_relacao_chamada(nova_revista["id_revista"], revista)
                inseridas_relacionamento += 1
                inseridas += 1

        except ValueError as e:
            print(f"Aviso: Ignorando revista com dados inválidos: {revista.get('nome')}. Erro: {e}")
            continue
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro ao processar revista: {e}; Revista: {revista}")

    return (inseridas, atualizadas, inseridas_relacionamento)


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
        chamada_json = processar_pdf_para_json(arquivo_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O arquivo enviado não contém um JSON válido.")

    if "chamadasdevolucao" not in chamada_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O conteúdo do JSON é inválido. A chave 'chamadasdevolucao' é obrigatória."
        )

    try:
        cd = chamada_json.get("chamadasdevolucao")
        if cd is None:
            raise KeyError("chamadasdevolucao")

        # campos esperados que você quer extrair
        pv_id = cd.get("ponto_venda_id")
        dl = cd.get("data_limite")

        missing = []
        if pv_id is None:
            missing.append("ponto_venda_id")
        if dl is None:
            missing.append("data_limite")

        if missing:
            raise KeyError(f"Campos faltando em chamadasdevolucao: {missing}")

        # Verifica tipo/valor de data_limite
        try:
            data_limite_dt = datetime.strptime(dl, "%Y-%m-%d")
        except Exception as e:
            raise ValueError(f"Formato inválido para data_limite: {dl}. Erro: {e}")

        dados_chamada = {
            "id_usuario": user["sub"],
            "ponto_venda_id": chamada_json["chamadasdevolucao"]["ponto_venda_id"],
            "data_limite": datetime.strptime(
                chamada_json["chamadasdevolucao"]["data_limite"], "%Y-%m-%d"
            ).date().isoformat(),
            "status": "aberta"
        }

        resposta_insert = supabase_admin.table("chamadasdevolucao").insert(dados_chamada).execute()
        chamada_criada = resposta_insert.data[0]
        id_chamada_criada = chamada_criada["id_chamada_devolucao"]

    except KeyError as e:
        detail = f"Chave ausente no JSON: {e}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    except ValueError as e:
        detail = f"Valor inválido no JSON: {e}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


    # AQUI ELE CADASTRA AS REVISTAS
    revistas_inseridas, revistas_atualizadas, inseridas_relacionamento = _cadastrar_revistas_db(chamada_json, supabase_admin, id_chamada_criada)

    return {
        "data": {
            "id_chamada": id_chamada_criada,
            "qtd_revistas_cadastradas": revistas_inseridas,
            "qtd_revistas_atualizadas": revistas_atualizadas,
            "qtd_revistas_chamada": inseridas_relacionamento,
        },
        "message": "Chamada criada e revistas cadastradas com sucesso."
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
        return {
            "data": resposta.data,
            "message": "Chamadas do usuário listadas com sucesso."
        }
    except Exception as e:
        print(f"Erro ao buscar chamadas no Supabase: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ocorreu um erro ao buscar as chamadas de devolução."
        )

@router.get("/alertas",response_model=List[AlertaChamadaNotificacao], summary="Alertas de chamadas com data_limite em ≤ N dias")
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

    saida: List[AlertaChamadaNotificacao] = []

    for r in rows:
        enc = r.get("data_limite")
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
            AlertaChamadaNotificacao(
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
