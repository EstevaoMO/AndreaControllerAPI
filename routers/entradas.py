from fastapi import APIRouter, UploadFile, HTTPException, File, Depends, status
from datetime import datetime
from supabase import Client
from typing import List, Dict, Any
import json

# (Importando o model de Devolucao para manter a tipagem, mas o ideal seria renomear)
from models.chamada_model import ChamadaDevolucaoResposta
from settings.settings import importar_configs
from services.auth import validar_token, pegar_usuario_admin
from services.extracao_entrada import processar_pdf_para_json
from routers.revistas import pegar_revistas
# Removido import de rapidfuzz, não é mais necessário


router = APIRouter(
    prefix="/entregas",
    tags=["Entregas"] # Mantido como Entregas (para o seu novo padrão "Entrada")
)

st = importar_configs()
URL_EXPIRATION_SECONDS = 30 * 24 * 60 * 60


def _cadastrar_revistas_db(entrega_json: Dict[str, Any], supabase_admin: Client, id_entrega_criada: str) -> tuple[int, int]:
    """
    Processa os dados das revistas do JSON e os insere/atualiza em lote.
    - Se a revista (nome + edição) existe, SOMA o estoque.
    - Se não existe, CRIA a revista com o estoque inicial.
    Retorna (novas_revistas_criadas, revistas_atualizadas).
    """
    lista_revistas_json = entrega_json.get("revistas", [])

    if not lista_revistas_json:
        return (0, 0)

    # 1. Buscar revistas existentes e criar um mapa de busca
    revistas_banco = pegar_revistas()
    revistas_existentes = revistas_banco.data if revistas_banco and revistas_banco.data else []

    # O mapa usa (nome_normalizado, edicao_str) como chave para busca rápida
    lookup_revistas: Dict[tuple[str, str], dict] = {}
    for rev in revistas_existentes:
        try:
            nome_norm = str(rev.get("nome", "")).strip().lower()
            edicao_str = str(rev.get("numero_edicao", "0"))
            if nome_norm:
                lookup_revistas[(nome_norm, edicao_str)] = rev
        except Exception as e:
            print(f"Aviso: Ignorando revista do banco com dados inválidos: {rev.get('id_revista')} - {e}")

    inseridas = 0
    atualizadas = 0

    # 2. Iterar sobre as revistas do JSON (Nota de Entrada)
    for revista_data in lista_revistas_json:
        try:
            # --- Limpeza dos dados do JSON ---
            nome = str(revista_data.get("nome", "")).strip()
            if not nome:
                print("Aviso: Ignorando revista sem nome no JSON.")
                continue

            nome_normalizado = nome.lower()

            # Garantir que numero_edicao seja tratado como string para a chave
            numero_edicao_json = revista_data.get("numero_edicao")
            if numero_edicao_json is None:
                numero_edicao_str = "0"
                numero_edicao_int = 0
            else:
                numero_edicao_str = str(int(numero_edicao_json))
                numero_edicao_int = int(numero_edicao_json)

            qtd_nova = int(revista_data.get("qtd_estoque") or 0)
            if qtd_nova < 0:
                qtd_nova = 0

            preco_capa_str = str(revista_data.get("preco_capa", "0.0")).replace(',', '.')
            preco_capa = float(preco_capa_str)

            id_revista_processada = None

            # --- Lógica Principal: Verificar se existe ---
            chave_busca = (nome_normalizado, numero_edicao_str)
            revista_existente = lookup_revistas.get(chave_busca)

            if revista_existente:
                # --- CASO 1: REVISTA EXISTE ---
                # Atualiza o estoque somando a quantidade nova
                try:
                    id_revista_existente = revista_existente["id_revista"]
                    estoque_atual = int(revista_existente.get("qtd_estoque") or 0)
                    novo_estoque = estoque_atual + qtd_nova

                    supabase_admin.table("revistas").update(
                        {"qtd_estoque": novo_estoque}
                    ).eq("id_revista", id_revista_existente).execute()

                    id_revista_processada = id_revista_existente
                    atualizadas += 1

                    # Atualiza o mapa local para consistência na mesma execução
                    lookup_revistas[chave_busca]["qtd_estoque"] = novo_estoque

                except Exception as e:
                    print(f"ERRO: Falha ao ATUALIZAR estoque para '{nome}' (Ed: {numero_edicao_str}). Erro: {e}")
                    continue

            else:
                # --- CASO 2: REVISTA NÃO EXISTE ---
                # Insere a nova revista no banco
                try:
                    revista_para_inserir = {
                        "nome": nome,
                        "numero_edicao": numero_edicao_int,
                        "qtd_estoque": qtd_nova, # Estoque inicial é a quantidade da nota
                        "preco_capa": preco_capa,
                        "url_revista": revista_data.get("url_revista") # (normalmente null)
                        # preco_liquido e codigo_barras serão null por padrão
                    }

                    revista_inserida_resp = supabase_admin.table("revistas").insert(revista_para_inserir).execute()

                    nova_revista = revista_inserida_resp.data[0]
                    id_revista_processada = nova_revista["id_revista"]
                    inseridas += 1

                    # Adiciona ao mapa local para evitar duplicatas na mesma execução
                    lookup_revistas[chave_busca] = nova_revista

                except Exception as e:
                    print(f"ERRO: Falha ao INSERIR nova revista '{nome}' (Ed: {numero_edicao_str}). Erro: {e}")
                    continue

            # --- 3. Associar à Tabela de Relacionamento ---
            # (Isso acontece tanto para revistas novas quanto atualizadas)
            if id_revista_processada:
                try:
                    supabase_admin.table("revistas_documentos_entrega").insert({
                        "id_documento_entrega": id_entrega_criada,
                        "id_revista": id_revista_processada,
                        "qtd_entregue": qtd_nova,
                    }).execute()
                except Exception as e:
                    print(f"ERRO: Falha ao INSERIR RELAÇÃO para '{nome}' (ID: {id_revista_processada}). Erro: {e}")

        except (ValueError, TypeError) as e:
            print(f"Aviso: Ignorando revista com dados inválidos no JSON: {revista_data.get('nome')}. Erro: {e}")
            continue

    return (inseridas, atualizadas)


@router.post("/cadastrar-entrega", status_code=status.HTTP_201_CREATED)
async def cadastrar_chamada(file: UploadFile = File(...), user: dict = Depends(validar_token), supabase_admin: Client = Depends(pegar_usuario_admin)):
    """
    Recebe um ARQUIVO PDF, salva-o no storage, interpreta seu conteúdo
    e insere os dados da entrega e das revistas no banco.
    """
    arquivo_bytes = await file.read()
    if not arquivo_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="O arquivo enviado está vazio.")

    try:
        # Usa o extrator específico de "Nota de Entrega"
        entrega_json = processar_pdf_para_json(arquivo_bytes)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Erro ao processar PDF: {str(e)}")

    if "notasentrega" not in entrega_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O conteúdo do JSON é inválido. A chave 'notasentrega' é obrigatória."
        )

    try:
        cd = entrega_json.get("notasentrega")
        if cd is None:
            raise KeyError("notasentrega")

        # campos esperados
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

        dados_entrega = {
            "id_usuario": user["sub"],
            "data_entrega": datetime.strptime(
                entrega_json["notasentrega"]["data"], "%Y-%m-%d"
            ).date().isoformat()
            # Adicione outros campos de 'notasentrega' se a tabela 'documentos_entrega' os tiver
            # ex: "ponto_venda_id": pv_id,
            # ex: "numero_nota": nota_id,
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
    except Exception as e:
        detail = f"Erro ao inserir documento de entrega no banco: {e}"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


    # AQUI ELE CADASTRA/ATUALIZA AS REVISTAS
    revistas_inseridas, revistas_atualizadas = _cadastrar_revistas_db(entrega_json, supabase_admin, id_entrega_criada)

    return {
        "data": {
            "id_entrega": id_entrega_criada,
            "qtd_novas_revistas_criadas": revistas_inseridas,
            "qtd_revistas_com_estoque_atualizado": revistas_atualizadas,
        },
        "message": "Entrega criada e estoque de revistas atualizado com sucesso."
    }

# (O endpoint /listar-chamadas-usuario foi removido pois pertencia a devoluções/chamadas)