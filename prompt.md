Você receberá um texto bruto com dados de revistas extraídos de OCR, onde os dados podem estar incompletos, fora de ordem ou misturados. Sua tarefa é reconhecer cada informação, identificar a qual campo da revista ela pertence, e estruturar todas as revistas em um JSON com o formato abaixo:

{
  "revistas": [
    {
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
    },
    ...
  ]
}

Lembre-se:
- Os dados podem vir desorganizados, incompletos ou em ordem diferente.
- Você deve agrupar as informações corretas para cada revista.
- Se algum campo estiver faltando, preencha com string vazia "".
- Mantenha o formato de data dd/mm/aaaa e preços com vírgula decimal.
- Não adicione explicações, retorne apenas o JSON válido.

Aqui estão exemplos de como o JSON final deve ficar para algumas revistas:

{
  "revistas": [
    {
      "produto": "A LANCA LENDÁRIA E O ESCUDO IMPENETRÁVEL",
      "subtitulo": "TOTOFUMI",
      "ean": "9786525915104 01",
      "edicao": "00001",
      "entrega": "04/06/2025",
      "pco_capa": "39,90",
      "rep": "2",
      "encalhe": "",
      "venda": "",
      "pco_liq": "27,930",
      "vir_venda": ""
    },
    {
      "produto": "A MISTERIOSA LOJA DE PENHORES",
      "subtitulo": "GO SUYOO",
      "ean": "97865935775",
      "edicao": "00001",
      "entrega": "25/06/2025",
      "pco_capa": "49,90",
      "rep": "2",
      "encalhe": "",
      "venda": "1",
      "pco_liq": "34,930",
      "vir_venda": ""
    },
    {
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
    }
  ]
}

Agora organize o texto abaixo seguindo essas regras e formato JSON esperado:
"""
{texto_bruto}
"""
