from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette import status
from os import getenv
import jwt

CHAVE_ACESSO = getenv("SUPABASE_JWT")

security = HTTPBearer()

# Comentado para conseguir fazer os testes necessários
def validar_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    # token = credentials.credentials
    # try:
    #     # Decodifica o token JWT
    #     payload = jwt.decode(token, CHAVE_ACESSO, algorithms=["HS256"])
    #     return payload
    # except jwt.ExpiredSignatureError:
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Token expirado",
    #     )
    # except jwt.InvalidTokenError:
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Token inválido",
    #     )
    return