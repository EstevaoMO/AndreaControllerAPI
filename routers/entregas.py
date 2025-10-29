from fastapi import APIRouter, UploadFile, HTTPException, File, Depends, status
from datetime import datetime
from supabase import Client
from typing import List, Dict, Any
import json

from models.chamada_model import ChamadaDevolucaoResposta
from settings.settings import importar_configs
from services.auth import validar_token, pegar_usuario_admin
from services.extracao_nota_entrega import processar_pdf_para_json
from routers.revistas import pegar_revistas
from rapidfuzz import fuzz


router = APIRouter(
    prefix="/entregas",
    tags=["Entregas"]
)

st = importar_configs()
URL_EXPIRATION_SECONDS = 30 * 24 * 60 * 60 


# Permissão de Admin para colocar arquivo no bucket
# Era aqui que estava dando problema, a lógica é que você precisa de permissão de adm para inserir dados em BUCKETs
# Usando a chave "service_key" conseguimos essa permissão, mas inserimos como um usuário diferente do usuário logado
# Por isso, dentro de 'docs', fiz os arquivos serem salvos dentro de uma pasta com o user_id
def _cadastrar_revistas_db(entrega_json: Dict[str, Any], supabase_admin: Client, id_entrega_criada: str) -> tuple[int, int]:
    """
    Processa os dados das revistas do JSON e os insere em lote na tabela 'revistas'.
    Retorna a quantidade de revistas inseridas com sucesso.
    """
    lista_revistas_json = entrega_json.get("revistas", [])

    if not lista_revistas_json:
        return (0, 0)
    
    revistas_banco = pegar_revistas()
    revistas_existentes = revistas_banco.data if revistas_banco and revistas_banco.data else []

    sufixos_padrao = ["c.p dura", "c.p. dura", "capa dura", "deluxe"]

    inseridas = 0
    atualizadas = 0

    def _normalizar_nome(nome: str) -> str:
        """Remove espaços e deixa tudo em minúsculo para comparação."""
        return nome.lower().strip()

    def _tem_sufixo(nome: str, sufixos_padrao: list[str]) -> bool:
        """Verifica se o nome contém algum sufixo da lista."""
        nome_lower = nome.lower()
        return any(sufixo in nome_lower for sufixo in sufixos_padrao)

    for revista_data in lista_revistas_json:
        try:
            nome = str(revista_data.get("nome", "")).strip()
            numero_edicao = int(revista_data.get("numero_edicao", 0))
            qtd_nova = int(revista_data.get("qtd_estoque") or 0)
            preco_capa = float(str(revista_data.get("preco_capa", "0.0")).replace(',', '.'))

            if not nome:
                continue

            nome_normalizado = _normalizar_nome(nome)
            tem_sufixo_novo = _tem_sufixo(nome, sufixos_padrao)

            # Tenta encontrar revista existente parecida
            revista_existente = None
            for rev in revistas_existentes:
                nome_banco = rev["nome"]
                nome_banco_norm = _normalizar_nome(nome_banco)
                tem_sufixo_banco = _tem_sufixo(nome_banco, sufixos_padrao)

                # Só compara se o número da edição for o mesmo)
                if str(rev.get("numero_edicao")) != str(numero_edicao):
                    continue

                # Se um tem sufixo e o outro não, são produtos diferentes
                if tem_sufixo_banco != tem_sufixo_novo:
                    continue

                # Comparação exata ou fuzzy
                similaridade = fuzz.token_sort_ratio(nome_normalizado, nome_banco_norm)
                if similaridade >= 95:
                    revista_existente = rev
                    break

            if revista_existente:
                # Atualiza estoque
                try:
                    novo_estoque = (revista_existente.get("qtd_estoque") or 0) + qtd_nova
                    supabase_admin.table("revistas").update(
                        {"qtd_estoque": novo_estoque}
                    ).eq("id_revista", revista_existente["id_revista"]).execute()
                    
                    supabase_admin.table("revistas_documentos_entrega").insert({
                        "id_documento_entrega": id_entrega_criada,
                        "id_revista": revista_existente["id_revista"],
                        "qtd_entregue": qtd_nova,
                    }).execute()
                    
                    revista_existente["qtd_estoque"] = novo_estoque
                    atualizadas += 1
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Erro de banco ao inserir revistas: {str(e)}"
                    )

            else:
                # Adiciona nova revista à lista de inserção
                try:
                    revista_para_inserir = {
                        "nome": nome,
                        "numero_edicao": numero_edicao,
                        "qtd_estoque": qtd_nova,
                        "preco_capa": preco_capa,
                    }
                    revista_inserida = supabase_admin.table("revistas").insert(revista_para_inserir).execute()
                    id_revista = revista_inserida.data[0]["id_revista"]
                    supabase_admin.table("revistas_documentos_entrega").insert({
                        "id_documento_entrega": id_entrega_criada,
                        "id_revista": id_revista,
                        "qtd_entregue": qtd_nova,
                    }).execute()
                    inseridas += 1
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Erro de banco ao inserir revistas: {str(e)}"
                    )

        except (ValueError, TypeError) as e:
            print(f"Aviso: Ignorando revista com dados inválidos: {revista_data.get('nome')}. Erro: {e}")
            continue

    return (inseridas, atualizadas)


@router.post("/cadastrar-entrega", status_code=status.HTTP_201_CREATED)
async def cadastrar_chamada(file: UploadFile = File(...), user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)):
    """
    Recebe um ARQUIVO JSON, salva-o no storage, interpreta seu conteúdo
    e insere os dados da entrega e das revistas no banco.
    """
    arquivo_bytes = await file.read()
    if not arquivo_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O arquivo enviado está vazio.")
    
    try:
        entrega_json = processar_pdf_para_json(arquivo_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O arquivo enviado não contém um JSON válido.")

    if "notasentrega" not in entrega_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O conteúdo do JSON é inválido. A chave 'notasentrega' é obrigatória."
        )

    try:
        cd = entrega_json.get("notasentrega")
        if cd is None:
            raise KeyError("notasentrega")

        # campos esperados que você quer extrair
        pv_id = cd.get("ponto_venda_id")
        nota_id = cd.get("nota_entrega_id")
        data = cd.get("data")

        missing = []
        if pv_id is None:
            missing.append("ponto_venda_id")
        if nota_id is None:
            missing.append("nota_entrega_id")
        if data is None:
            missing.append("data")

        if missing:
            raise KeyError(f"Campos faltando em notasentrega: {missing}")

        # Verifica tipo/valor de data
        try:
            data_limite_dt = datetime.strptime(data, "%Y-%m-%d")
        except Exception as e:
            raise ValueError(f"Formato inválido para data: {data}. Erro: {e}")

        dados_entrega = {
            "id_usuario": user["sub"],
            "data_entrega": datetime.strptime(
                entrega_json["notasentrega"]["data"], "%Y-%m-%d"
            ).date().isoformat()
        }

        resposta_insert = supabase_admin.table("documentos_entrega").insert(dados_entrega).execute()
        entrega_criada = resposta_insert.data[0]
        id_entrega_criada = entrega_criada["id_documento_entrega"]

    except KeyError as e:
        detail = f"Chave ausente no JSON: {e}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    except ValueError as e:
        detail = f"Valor inválido no JSON: {e}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


    # AQUI ELE CADASTRA AS REVISTAS
    revistas_inseridas, revistas_atualizadas = _cadastrar_revistas_db(entrega_json, supabase_admin, id_entrega_criada)
    
    return {
        "data": {
            "id_entrega": id_entrega_criada,
            "qtd_revistas_cadastradas": revistas_inseridas,
            "qtd_revistas_atualizadas": revistas_atualizadas,
        },
        "message": "Entrega criada e revistas cadastradas com sucesso."
    }

# @router.get("/listar-chamadas-usuario")
# async def listar_chamadas_por_usuario(user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)) -> List[ChamadaDevolucaoResposta]:
#     """
#     Lista todas as chamadas de devolução associadas ao usuário autenticado.
#     """
#     try:
#         resposta = (
#             supabase_admin.table("notasentrega")
#             .select("*")
#             .eq("id_usuario", user["sub"])
#             .order("data_limite", desc=True)
#             .execute()
#         )
#         return {
#             "data": resposta.data,
#             "message": "Chamadas do usuário listadas com sucesso."
#         }
#     except Exception as e:
#         print(f"Erro ao buscar chamadas no Supabase: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Ocorreu um erro ao buscar as chamadas de devolução."
#         )