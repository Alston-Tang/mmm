from __future__ import annotations

from functools import lru_cache

import plaid
from plaid.api import plaid_api

from app.config import get_settings

_ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "development": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


@lru_cache(maxsize=1)
def get_plaid_client() -> plaid_api.PlaidApi:
    settings = get_settings()
    env_name = settings.plaid_env.lower()
    if env_name not in _ENV_MAP:
        raise RuntimeError(f"Invalid PLAID_ENV={env_name!r}")

    configuration = plaid.Configuration(
        host=_ENV_MAP[env_name],
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))
