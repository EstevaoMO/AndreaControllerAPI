# Padronização de Payloads da AndreaControllerAPI

Este documento estabelece o padrão para os payloads de requisição e resposta da API, visando a consistência e a clareza na comunicação entre o cliente e o servidor.

## 1. Payload Padrão de Sucesso

Toda resposta de sucesso (HTTP status `2xx`) deve seguir a estrutura abaixo. Isso garante que o cliente sempre saiba onde encontrar os dados principais da resposta.

**Estrutura:**

```json
{
  "data": <tipo_variado>,
  "message": "string"
}
```

- **`data`**: Contém o corpo principal da resposta. Pode ser um objeto, um array de objetos ou `null` caso o endpoint não retorne dados (ex: em uma operação de cadastro que retorna apenas uma mensagem).
  - Para GET, mostra o conteúdo pedido;
  - Para POST, contém null;
- **`message`**: Uma mensagem descritiva sobre o sucesso da operação.

## 2. Payload Padrão de Erro

A principal regra é **sempre utilizar as constantes de status do módulo `fastapi.status`** para garantir a consistência dos códigos.

**Estrutura:**

```json
{
  "detail": "string"
}
```

- **`detail`**: Uma mensagem clara e concisa sobre o erro que ocorreu.
  - Para 500 (Internal Server Error), ele passa os details
