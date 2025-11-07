import re
from io import BytesIO
from typing import Optional, Tuple
from pypdf import PdfReader
from datetime import datetime

def _extrair_texto_pdf_pypdf(file_bytes: bytes) -> Optional[str]:
    """
    Extrai texto de todas as páginas de um PDF (PyPDF) para a pré-verificação.
    """
    try:
        reader = PdfReader(BytesIO(file_bytes))
        texto = []
        for page in reader.pages:
            t = page.extract_text() or ""
            texto.append(t)
        return "\n".join(texto).strip()
    except Exception as e:
        print(f"[ERRO] Falha ao ler PDF com PyPDF: {e}")
        return None

def _formatar_data_iso(data_str: str) -> str:
    """Converte DD/MM/YYYY para YYYY-MM-DD."""
    try:
        return datetime.strptime(data_str, "%d/%m/%Y").date().isoformat()
    except ValueError:
        raise ValueError(f"Formato de data inválido: '{data_str}'. Esperado DD/MM/YYYY.")

def _extrair_pdv(texto: str) -> Optional[str]:
    """Extrai o ID do ponto de venda (PDV) do texto."""
    # Tenta a lógica de "Ponto : 48507" ou "Ponto4 :8507"
    # Procura por "Ponto", um dígito opcional (Ponto4), lixo, e depois os números
    match = re.search(r"Ponto\s*(\d)?\s*[:\-]?\s*(\d[\s\d]*)", texto, re.IGNORECASE)
    if match:
        prefixo = match.group(1) or ""
        sufixo = re.sub(r"\s", "", match.group(2) or "")
        pdv = f"{prefixo}{sufixo}"

        # Garante que é um número razoável (ex: 48507)
        if pdv.isdigit() and len(pdv) >= 4:
            return pdv
    return None

def extrair_dados_devolucao_local(file_bytes: bytes) -> str:
    """
    Extrai localmente data_limite_iso de uma Devolução.
    Levanta ValueError se os campos não forem encontrados.
    """
    texto = _extrair_texto_pdf_pypdf(file_bytes)
    if not texto:
        raise ValueError("Não foi possível extrair texto do PDF (PyPDF).")

    # Extrair Data Limite (Específico: "Data da chamada")
    match_data = re.search(r"Data da chamada\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
    if not match_data:
        raise ValueError("Não foi possível localizar a 'Data da chamada' no PDF.")

    data_iso = _formatar_data_iso(match_data.group(1))
    return data_iso

def extrair_dados_entrada_local(file_bytes: bytes) -> Tuple[str, str]:
    """
    Extrai localmente (data_entrega_iso, ponto_venda_id) de uma Entrada.
    Levanta ValueError se os campos não forem encontrados.
    """
    texto = _extrair_texto_pdf_pypdf(file_bytes)
    if not texto:
        raise ValueError("Não foi possível extrair texto do PDF (PyPDF).")

    # 1. Extrair Data de Entrega (Genérico: "Data :")
    # (Tenta evitar "Data da chamada" que é da devolução)
    match_data = None
    # Procura por "Data :" em linhas que não contenham "chamada"
    for line in texto.split('\n'):
        if "chamada" not in line.lower():
            # \bData = "boundary" Data, evita "Candidata"
            match = re.search(r"\bData\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})", line, re.IGNORECASE)
            if match:
                match_data = match
                break

    if not match_data:
        raise ValueError("Não foi possível localizar a 'Data' de entrega no PDF.")

    data_iso = _formatar_data_iso(match_data.group(1))

    # 2. Extrair Ponto de Venda
    pdv = _extrair_pdv(texto)
    if not pdv:
         raise ValueError("Não foi possível localizar o 'Ponto de Venda' no PDF.")

    return (data_iso, pdv)