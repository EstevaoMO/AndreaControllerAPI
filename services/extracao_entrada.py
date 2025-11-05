import json
import re
from typing import Optional
import pdfplumber
import google.generativeai as genai
from settings.settings import importar_configs
from io import BytesIO

st = importar_configs()

PROMPT_INSTRUCOES = """
Você é um extrator de dados. Dado um texto bruto (OCR) de uma “Chamada de Encalhe”,
retorne APENAS um JSON válido (sem comentários, sem texto extra) com duas chaves:
"notasentrega" e "revistas". Não invente dados; se faltar, use null.

Esquema de saída:

{
  "notasentrega": {
    "id_nota_entrega": null,
    "id_usuario": null,
    "ponto_venda_id": "string|null",
    "nota_entrega_id": "string|null",
    "data": "YYYY-MM-DD|null",
    "url_documento": "string|null"
  },
  "revistas": [
    {
      "id_revista": null,
      "nome": "string",
      "numero_edicao": int|null,
      "qtd_estoque": 0,
      "preco_capa": 0,
      "url_revista": null
    }
  ]
}

REGRAS:
- Cabeçalho → notasentrega:
  - ponto_venda_id: identificador do PDV. Preferência: texto após “Ponto :”.
  - nota_entrega_id: identificador da nota de entrega. Preferência: número junto de "Nº”. 
    Se ausente, use o nome do estabelecimento (ex.: “Andea Bloise”).
    OBS: o identificador da nota de entrega não é igual ao do ponto de venda.
  - data: valor após “Data :” (DD/MM/AAAA) → ISO YYYY-MM-DD.
  - url_documento: null
  - id_nota_entrega, id_usuario: null
- Tabela → revistas (uma entrada por produto):
  - nome: título do produto (ignore linhas de categoria/autores/variante)
  - numero_edicao: coluna “Edição”
  - qtd_estoque: valor da coluna "Quant.”
  - preco_capa: coluna “Pço.Capa” (converter 13,90 → 13.90)
  - url_revista: null
- Ignore campos que não existem no banco (Encalhe, Venda, Vlr.Venda, categoria/autores/variantes).
- Datas: DD/MM/AAAA → YYYY-MM-DD
- Números: usar ponto como decimal, sem separador de milhar
- ATENÇÃO: a coluna *Quant.* (qtd_estoque) é SEMPRE um número inteiro pequeno (ex.: 1, 2, 3, 10, 25).
- ATENÇÃO: a coluna *preco_capa* é SEMPRE valor monetário com DUAS casas decimais (ex.: 6.99, 13.90, 213.90).
- NUNCA confunda quantidade (inteiro) com preço (decimal).
- Se no texto houver dúvida, priorize: 
    - qtd_estoque deve ser inteiro entre 0 e 9999
    - preco_capa deve ser decimal com vírgula → ponto.
- Una linhas quebradas de um mesmo produto antes de montar o registro.
- Retorne SOMENTE o JSON.
"""

def extrair_texto_pdf_bytes(file_bytes: bytes) -> Optional[str]:
    """Extrai texto de todas as páginas de um PDF a partir de um arquivo binário."""
    texto = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            # layout=True preserva espaços entre colunas
            texto_page = page.extract_text(layout=True) or ""
            texto.append(texto_page)
    return "\n".join(texto).strip()

def chamar_gemini(texto_bruto: str) -> str:
    """Chama o Gemini e pede a resposta em JSON puro."""
    genai.configure(api_key=st.API_KEY)
    model = genai.GenerativeModel(
        st.MODEL_NAME,
        generation_config={"response_mime_type": "application/json"},
    )
    content = f"{PROMPT_INSTRUCOES}\n\nTEXTO BRUTO A PROCESSAR:\n---\n{texto_bruto}\n---"
    resp = model.generate_content(content)
    return (resp.text or "").strip()

def normalizar_tipos(dados: dict) -> dict:
    """Converte strings 'null' -> None, números em string -> int/float."""
    def conv(v):
        if isinstance(v, str):
            v_strip = v.strip().lower()
            if v_strip in {"null", "none", ""}:
                return None
            # tenta int
            if v.isdigit():
                return int(v)
            # tenta float com ponto
            try:
                return float(v)
            except ValueError:
                return v
        elif isinstance(v, list):
            return [conv(x) for x in v]
        elif isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        return v
    return conv(dados)

def parse_json_resposta(s: str) -> dict:
    s = re.sub(r"^(?:json)?\s*|\s*$", "", s, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        data = json.loads(s)
    except json.JSONDecodeError as e:
        trecho = s[:1000]
        raise ValueError(f"Resposta não é JSON válido.\nErro: {e}\nTrecho inicial:\n{trecho}\n")
    if not isinstance(data, dict) or "notasentrega" not in data or "revistas" not in data:
        raise ValueError("JSON não contém as chaves necessárias: 'notasentrega' e 'revistas': ", data)
    
    return normalizar_tipos(data)
    
# Função de extração
def processar_pdf_para_json(file_bytes: bytes) -> dict:
    """
    Função principal: recebe PDF binário, processa e retorna JSON estruturado.
    """
    texto = extrair_texto_pdf_bytes(file_bytes)
    if not texto:
        raise ValueError("[ERRO] Sem texto para processar.")

    resposta = chamar_gemini(texto)
    dados = parse_json_resposta(resposta)
    print(dados)
    return dados