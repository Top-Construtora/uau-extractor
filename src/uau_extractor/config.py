"""Configuração: carrega credenciais e endpoints da API UAU/Trinus do ambiente (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # API Gateway Trinus (gera access_token OAuth2 client_credentials)
    gateway_url: str
    # Base da UAUAPi (endpoints de dados)
    api_base_url: str
    # Token de integração da Globaltec -> header X-Integration-Authorization
    token_integracao: str
    # client_id do API Gateway Trinus
    client_id: str
    # base64(client_id:secret_id) -> header "Authorization: Basic <...>" do gateway
    trinus_basic: str
    # Usuário/senha do sistema UAU (AutenticarUsuario)
    login: str
    senha: str
    # Destino: Postgres Supabase
    db_url: str = ""
    # Supabase Storage (snapshot do JSON bruto) — opcional
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_bucket: str = "uau-raw"


def carregar() -> Settings:
    """Lê o ambiente e devolve Settings. Levanta KeyError se faltar variável obrigatória."""
    return Settings(
        gateway_url=os.environ.get("UAU_GATEWAY_URL", "https://api.trinus.co"),
        api_base_url=os.environ.get("UAU_API_BASE_URL", "https://api.trinus.co/uau/v1"),
        token_integracao=os.environ["UAU_TOKEN_INTEGRACAO"],
        client_id=os.environ["UAU_CLIENT_ID"],
        trinus_basic=os.environ["UAU_TRINUS_BASIC"],
        login=os.environ["UAU_LOGIN"],
        senha=os.environ["UAU_SENHA"],
        db_url=os.environ.get("SUPABASE_DB_URL", ""),
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_service_key=os.environ.get("SUPABASE_SERVICE_KEY", ""),
        supabase_bucket=os.environ.get("SUPABASE_BUCKET", "uau-raw"),
    )
