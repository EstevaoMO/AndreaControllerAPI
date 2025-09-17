from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from settings.settings import importar_configs
from starlette import status
from os import getenv
import jwt

security = HTTPBearer()
st = importar_configs()

def validar_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            st.SUPABASE_JWT.strip(),
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["exp", "iat", "sub"]},
        )
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
