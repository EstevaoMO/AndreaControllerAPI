from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from settings.settings import importar_configs
from supabase import Client, create_client
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

# Valida o Token e devolve o User
def pegar_usuario(user: dict = Depends(validar_token)) -> dict:
    """Valida o token e retorna os dados do usuário."""
    if not user or "sub" not in user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Token inválido ou não fornecido"
        )
    return user

def pegar_usuario_admin() -> Client:
    """Retorna um cliente Supabase com permissões de administrador (service_key)."""
    return create_client(st.SUPABASE_URL, st.SUPABASE_SERVICE_KEY)
