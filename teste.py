import argparse
from io import BytesIO
import sys
from pathlib import Path
from typing import Optional
from pypdf import PdfReader


def extrair_texto_pdf_bytes(file_bytes: bytes) -> Optional[str]:
    """Extrai texto de todas as páginas de um PDF a partir de um arquivo binário."""
    try:
        reader = PdfReader(BytesIO(file_bytes))
        texto = []
        for page in reader.pages:
            t = page.extract_text() or ""
            texto.append(t)
        return "\n".join(texto).strip()
    except Exception as e:
        print(f"[ERRO] Falha ao ler PDF: {e}")
        return None

def processar_pdf_para_bytes(file_bytes: bytes) -> dict:
	"""
	Função principal: recebe PDF binário, processa e retorna a data após 'Data da chamada'.
	"""
	import re
	texto = extrair_texto_pdf_bytes(file_bytes)
	if not texto:
		raise ValueError("[ERRO] Sem texto para processar.")

	# Procurar a data após 'Data da chamada'
	match = re.search(r"Data da chamada\s*[:\-]?\s*([0-9]{2}/[0-9]{2}/[0-9]{4})", texto, re.IGNORECASE)
	if match:
		return match.group(1)
	else:
		raise ValueError("[ERRO] Data da chamada não encontrada.")


def ler_arquivo_bytes(caminho: Path) -> bytes:
	if not caminho.exists():
		raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")
	if not caminho.is_file():
		raise IsADirectoryError(f"Caminho não é um arquivo: {caminho}")
	return caminho.read_bytes()


def main():
	parser = argparse.ArgumentParser(description="Comparar dois PDFs usando processar_pdf_para_bytes")
	parser.add_argument("pdf1", help="Caminho para o primeiro arquivo PDF")
	parser.add_argument("pdf2", help="Caminho para o segundo arquivo PDF")
	args = parser.parse_args()

	p1 = Path(args.pdf1)
	p2 = Path(args.pdf2)

	try:
		b1 = ler_arquivo_bytes(p1)
		b2 = ler_arquivo_bytes(p2)

		data1 = processar_pdf_para_bytes(b1)
		data2 = processar_pdf_para_bytes(b2)

		if data1 == data2:
			print(f"data-limite: {data1}")
			sys.exit(0)
		else:
			print(f"data-limite-diferentes: {data1} | {data2}")
			sys.exit(1)

	except Exception as e:
		print(f"[ERRO] {e}")
		sys.exit(2)


if __name__ == "__main__":
	main()