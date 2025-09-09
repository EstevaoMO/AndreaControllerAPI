from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette import status
import os
import jwt

CHAVE_BANCO = os.getenv("SUPABASE_JWT_SECRET", "CHAVE_SECRETA")

security = HTTPBearer()

def validar_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # Decodifica o token JWT
        payload = jwt.decode(token, CHAVE_BANCO, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )

def OCRMockado(arquivo : __file__):
    return