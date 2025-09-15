import json
import os

def teste_extracao(dados_json: dict) -> list:
    """
    Extrai, transforma e formata os dados das revistas de um JSON de chamada
    para o padrão da tabela 'Revistas' do banco de dados.

    Args:
        dados_json: O dicionário python carregado do arquivo JSON.

    Returns:
        Uma lista de dicionários, onde cada dicionário representa uma revista
        pronta para ser inserida no banco de dados.
    """
    revistas_formatadas = []
    lista_revistas_do_json = dados_json.get("revistas", [])

    if not lista_revistas_do_json:
        print("A chave 'revistas' não foi encontrada ou está vazia no JSON.")
        return []

    print(f"Encontradas {len(lista_revistas_do_json)} revistas para processar...\n")

    for revista in lista_revistas_do_json:
        # --- Tratamento e Conversão de Dados ---

        # Converte 'numero_edicao' para inteiro
        try:
            edicao = int(revista.get("edicao", 0))
        except (ValueError, TypeError):
            edicao = 0

        # Converte 'rep' (repartido/entregue) para 'qtd_estoque'
        try:
            # Usamos 'rep' como a quantidade que o ponto de venda recebeu.
            estoque = int(revista.get("rep") or 0)
        except (ValueError, TypeError):
            estoque = 0

        # Converte preços (strings com vírgula) para float
        try:
            preco_c = float(str(revista.get("pco_capa", "0.0")).replace(',', '.'))
        except (ValueError, TypeError):
            preco_c = 0.0

        try:
            preco_l = float(str(revista.get("pco_liq", "0.0")).replace(',', '.'))
        except (ValueError, TypeError):
            preco_l = 0.0
        
        # Limpa o código de barras, removendo espaços
        cod_barras = str(revista.get("ean", "")).replace(" ", "")

        # --- Mapeamento para o formato da tabela ---
        revista_mapeada = {
            "nome": revista.get("produto"),
            "apelido_revista": revista.get("subtitulo"),
            "numero_edicao": edicao,
            "codigo_barras": cod_barras,
            "qtd_estoque": estoque,
            "preco_capa": preco_c,
            "preco_liquido": preco_l,
        }
        revistas_formatadas.append(revista_mapeada)

    return revistas_formatadas

# --- Bloco de Execução Principal do Teste ---
if __name__ == "__main__":
    nome_arquivo = "json-img1[1].json"

    if not os.path.exists(nome_arquivo):
        print(f"ERRO: Arquivo '{nome_arquivo}' não encontrado.")
        print("Certifique-se de que ele está no mesmo diretório que este script.")
    else:
        try:
            with open(nome_arquivo, 'r', encoding='utf-8') as f:
                dados_arquivo_json = json.load(f)

            # Chama a função de processamento
            revistas_prontas = teste_extracao(dados_arquivo_json)

            # Imprime o resultado de forma legível
            print("--- Resultado do Mapeamento (simulando o que será enviado ao DB) ---")
            print(json.dumps(revistas_prontas, indent=4, ensure_ascii=False))

        except json.JSONDecodeError:
            print(f"ERRO: O arquivo '{nome_arquivo}' contém um JSON inválido.")
        except Exception as e:
            print(f"Ocorreu um erro inesperado: {e}")