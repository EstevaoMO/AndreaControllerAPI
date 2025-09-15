import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Obtém as credenciais do Supabase do ambiente
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_API_KEY")

# Cria o cliente Supabase
supabase: Client = create_client(url, key)

def registrar_usuario():
    """Registra um novo usuário no Supabase."""
    email = input("Digite o e-mail para registro: ")
    password = input("Digite a senha para registro: ")
    try:
        # A função sign_up cria o usuário
        resposta = supabase.auth.sign_up({
            "email": email,
            "password": password,
        })
        print("\nUsuário registrado com sucesso!")
        print("Por favor, verifique seu e-mail para confirmar o registro.")
        print("Dados do usuário:", resposta.user)
    except Exception as e:
        print(f"\nErro no registro: {e}")

def login_usuario():
    """Faz o login de um usuário e exibe o token de acesso."""
    email = input("Digite seu e-mail para login: ")
    password = input("Digite sua senha para login: ")
    try:
        # A função sign_in_with_password autentica o usuário
        resposta = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
        
        # O token de acesso está dentro do objeto da sessão
        access_token = resposta.session.access_token
        
        print("\nLogin realizado com sucesso!")
        print("\n--- SEU TOKEN DE ACESSO (JWT) ---")
        print(access_token)
        print("\nUse este token no cabeçalho 'Authorization' como 'Bearer <token>'")
        
    except Exception as e:
        print(f"\nErro no login: {e}")

if __name__ == "__main__":
    print("O que você deseja fazer?")
    print("1. Registrar um novo usuário")
    print("2. Fazer login e obter o token")
    
    escolha = input("Digite sua escolha (1 ou 2): ")
    
    if escolha == '1':
        registrar_usuario()
    elif escolha == '2':
        login_usuario()
    else:
        print("Escolha inválida.")