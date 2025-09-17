from paddleocr import PaddleOCR
import json
import re
import Levenshtein
import os
import unicodedata
import requests
from settings.settings import importar_configs

st = importar_configs()

ocr = PaddleOCR(lang='pt')

def remover_acentos(texto):
    """Remove acentuação de um texto para facilitar busca."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )

def extrair_valor(padrao, texto, grupo=1, default="NÃO ACHOU NADAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"):
    """
    Função auxiliar para extrair valor com regex de forma segura,
    ignorando acentos ao buscar, e retornando texto original com possivel acento.
    """
    texto_sem_acentos = remover_acentos(texto).lower()
    padrao_sem_acentos = remover_acentos(padrao).lower()

    # Faz busca no texto sem acento
    match = re.search(padrao_sem_acentos, texto_sem_acentos)

    if not match:
        return default

    if grupo == 0:  # pegar texto completo correspondido
        inicio, fim = match.start(), match.end()
        return texto[inicio:fim].strip()

    if len(match.groups()) >= grupo:
        # Capture o trecho sem acentos do grupo e tentamos localizar ele no texto original para preservar acentos
        valor_sem_acentos = match.group(grupo)
        pos = texto_sem_acentos.find(valor_sem_acentos)
        if pos != -1:
            # Retorna trecho do texto original que corresponde a parte achada
            return texto[pos:pos+len(valor_sem_acentos)].strip()
        else:
            # Caso não ache, devolve valor sem acentos mesmo
            return valor_sem_acentos.strip()

    return default

def extrair_revistas_de_texto(texto_completo):
    linhas = texto_completo.splitlines()

    # Encontrar o índice onde começa a seção de revistas
    try:
        idx_inicio = next(i for i, linha in enumerate(linhas) if "REVISTAS" in linha)
        idx_fim = next(i for i, s in enumerate(linhas) if s.lower().startswith("quant itens"))
        idx_cabecalho_fim = next((i for i, s in enumerate(linhas[idx_inicio:idx_fim]) if 'VIr.Venda' in s), 0)
        linhas_revistas = linhas[idx_inicio + idx_cabecalho_fim + 1 : idx_fim]
    except StopIteration:
        return []  # Não achou seção revistas

    return '\n'.join(linhas_revistas)

def obter_json_revistas(prompt):
    """
    Envia o prompt para a API de IA e retorna o JSON extraído da resposta.
    """
    url = "https://openrouter.ai/api/v1/completions"

    payload = {
        "model": "mistralai/mistral-7b-instruct:free",
        "prompt": prompt
    }
    headers = {
        "Authorization": "Bearer {}".format(st.OPENROUTER_API),
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    texto = response.json()['choices'][0]['text']
    return texto

def remover_json_da_resposta(texto_ia):
    # Procura o conteúdo entre ``````
    padrao = r"```json(.*?)```"
    match = re.search(padrao, texto_ia, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        # Se não encontrar com json, tenta pegar entre ``````
        padrao_simples = r"``````"
        match_simples = re.search(padrao_simples, texto_ia, re.DOTALL)
        if match_simples:
            return match_simples.group(1)
    # Caso não ache nada, retorna o texto original
    return texto_ia.strip()

def transformar_texto_em_json(texto_extraido):
    """
    Analisa o texto bruto do OCR e o transforma em um dicionário estruturado (JSON).
    """

    texto_completo = texto_extraido
    
    json_final = {
        "empresa": {
        "nome": "APACHE LOGÍSTICA",
        "endereco": "Rua Prefeito Olímpio de Melo n° 1828",
        "bairro":"Benfica",
        "cidade": "Rio de Janeiro",
        "estado": "RJ",
        "cep": "20930-005",
        "telefones": ""
        },
        "chamada_encalhe": {
            "ce": "", 
            "data_da_chamada": "", 
            "dia_semana": "", 
            "ponto": "",
            "cliente": {
                "nome": "", 
                "endereco": "", 
                "telefone": "", 
                "cep": "", 
                "bairro": "Barra da Tijuca", 
                "cidade": "Rio de Janeiro"
            },
            "local_entrega": "", 
            "horario": "", 
            "responsavel": "", 
            "numero_chamada": ""
        },
        "solucao": "", 
        "revistas": [],
        "totais": {"quantidade_itens": "", "total_entregue": "", "volume": "", "total_entregue_geral": "", "volume_geral": ""},
        "observacoes": "", 
        "data_documento": ""
    }

    json_final["data_documento"] = extrair_valor(r'(\d{2}/\d{2}/\d{4}) \d{2}.\d{2}.\d{2}P.*:', texto_completo)

    try:
        limite_cabecalho = texto_completo.index('CHAMADA DE ENCALHE')
        texto_cabecalho = texto_completo[:limite_cabecalho]
    except ValueError:
        texto_cabecalho = texto_completo
    json_final["empresa"]["telefones"] = re.findall(r"(\(\d{2}\)\s*\d{4,5}[-.\s]*\d{4})", texto_cabecalho)
    
    json_final["chamada_encalhe"]["ce"] = extrair_valor(r"CE\s*:\s*(\d+)", texto_completo)
    json_final["chamada_encalhe"]["data_da_chamada"] = extrair_valor(r"Data da chamada\s*(\d{2}/\d{2}/\d{4})", texto_completo)
    json_final["chamada_encalhe"]["dia_semana"] = extrair_valor(r"(Terça feira)", texto_completo)
    json_final["chamada_encalhe"]["ponto"] = extrair_valor(r"Pont.*?\s*(\d+)", texto_completo)
    json_final["chamada_encalhe"]["numero_chamada"] = json_final["chamada_encalhe"]["ponto"]
    
    json_final["chamada_encalhe"]["cliente"]["nome"] = extrair_valor(r"Pont.*?\d+\s+(.*?)\s+CEP", texto_completo)
    json_final["chamada_encalhe"]["cliente"]["endereco"] = extrair_valor(r"(Avenida Armando Lombardi, \d+)", texto_completo)
    json_final["chamada_encalhe"]["cliente"]["telefone"] = extrair_valor(r"Tel:\s*([()\d-]+)", texto_completo)
    json_final["chamada_encalhe"]["cliente"]["cep"] = extrair_valor(r"CEP\s*(\d{5}-\d{3})", texto_completo)
    
    json_final["chamada_encalhe"]["responsavel"] = extrair_valor(r"Resp\.:\s*(.*)", texto_completo)
    json_final["solucao"] = extrair_valor(r"(\d+\s+SOLUÇÃO\s+\d+)", texto_completo)

    json_final["totais"]["quantidade_itens"] = extrair_valor(r"Quant itens\s+(\d+)", texto_completo)
    json_final["totais"]["total_entregue"] = extrair_valor(r"Total entre(?:g|q)ue:\s*([\d.,]+)", texto_completo)
    json_final["totais"]["volume"] = extrair_valor(r"Vols.*\s*.*\s*:\s*(\d+)", texto_completo)
    json_final["totais"]["total_entregue_geral"] = extrair_valor(r"Total entregue geral:\s*([\d.,]+)", texto_completo)
    json_final["totais"]["volume_geral"] = extrair_valor(r"Vols\.\(geral\):\s*(\d+)", texto_completo)
    
    obs_match = extrair_valor(r"Observações\s*(PREZADO JORNALEIRO[\s\S]*)", texto_completo)
    if obs_match:
        observacao_limpa = obs_match.split('---')[0]
        json_final["observacoes"] = " ".join(observacao_limpa.split()).strip()


    revistas_texto_bruto = extrair_revistas_de_texto(texto_completo)

    prompt = f"""
    Você receberá um texto bruto com dados de revistas extraídos de OCR, onde os dados podem estar incompletos, fora de ordem ou misturados. Sua tarefa é reconhecer cada informação, identificar a qual campo da revista ela pertence, e estruturar todas as revistas em um JSON com o formato abaixo:

    {{
    "revistas": [
        {{
        "produto": "Nome do Produto",
        "subtitulo": "Subtítulo ou autor",
        "ean": "Código EAN",
        "edicao": "Número da edição",
        "entrega": "Data de entrega no formato dd/mm/aaaa",
        "pco_capa": "Preço de capa, com vírgula decimal",
        "rep": "Quantidade de repostas",
        "encalhe": "Quantidade de encalhe",
        "venda": "Quantidade de venda (pode ser vazio)",
        "pco_liq": "Preço líquido, com vírgula decimal",
        "vir_venda": "Quantidade virada para venda (pode ser vazio)"
        }}
    ]
    }}

    Lembre-se:
    - Os dados podem vir desorganizados, incompletos ou em ordem diferente.
    - Você deve agrupar as informações corretas para cada revista.
    - Se algum campo estiver faltando, preencha com string vazia "".
    - Mantenha o formato de data dd/mm/aaaa e preços com vírgula decimal.
    - Não adicione explicações, retorne apenas o JSON válido.

    Aqui estão exemplos de como o JSON final deve ficar para algumas revistas:

    {{
    "revistas": [
        {{
        "produto": "A LANCA LENDÁRIA E O ESCUDO IMPENETRÁVEL",
        "subtitulo": "TOTOFUMI",
        "ean": "9786525915104 01",
        "edicao": "00001",
        "entrega": "04/06/2025",
        "pco_capa": "39,90",
        "rep": "2",
        "encalhe": "1",
        "venda": "",
        "pco_liq": "27,930",
        "vir_venda": ""
        }},
        {{
        "produto": "A MISTERIOSA LOJA DE PENHORES",
        "subtitulo": "GO SUYOO",
        "ean": "97865935775",
        "edicao": "00001",
        "entrega": "25/06/2025",
        "pco_capa": "49,90",
        "rep": "2",
        "encalhe": "1",
        "venda": "1",
        "pco_liq": "34,930",
        "vir_venda": ""
        }},
        {{
        "produto": "A RECREATIVA",
        "subtitulo": "JOÃO FONSCA, TENISTA Nº 1 DO BRASIL",
        "ean": "977141397900900496",
        "edicao": "00496",
        "entrega": "23/07/2025",
        "pco_capa": "38,90",
        "rep": "2",
        "encalhe": "",
        "venda": "",
        "pco_liq": "27,230",
        "vir_venda": ""
        }}
    ]
    }}

    Agora, organize o texto abaixo seguindo essas regras e o formato JSON esperado, e retorne apenas o JSON válido, sem explicações ou comentários:

    \"\"\"
    {revistas_texto_bruto}
    \"\"\"
    """

    revistas = remover_json_da_resposta(obter_json_revistas(prompt))
    json_final["revistas"] = json.loads(revistas).get("revistas", [])

    return json_final

# ======================================================================
# Código principal para executar OCR e transformar em JSON
# ======================================================================
caminho_img = "tmp/imagem_digitalizada.jpeg"

if not os.path.exists(caminho_img):
    print(f"A imagem não foi encontrada em '{caminho_img}'")
else:
    print(f"Lendo a imagem: {caminho_img}...")
    resultados = ocr.predict(caminho_img)
    print("Texto extraído com sucesso.")

if resultados and resultados[0]:
    print("--- Texto Extraído ---")
    
    lista_de_textos = resultados[0]['rec_texts']
    
    # for texto in lista_de_textos:
    #     print(texto)
        
    print("----------------------")
else:
    print("Nenhum texto foi detectado ou a célula anterior não foi executada.")

if lista_de_textos:
    texto_completo_extraido = "\n".join(lista_de_textos)

    print("--- Transformando em JSON Estruturado ---")
    json_estruturado = transformar_texto_em_json(texto_completo_extraido)

    # salva em um arquivo JSON
    with open("chamada.json", "w", encoding="utf-8") as f:
        json.dump(json_estruturado, f, indent=4, ensure_ascii=False)
        
    print("JSON salvo em 'saida.json'")
else:
    print("Execute a célula de OCR primeiro para gerar a 'lista_de_textos'.")

