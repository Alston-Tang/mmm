from __future__ import annotations

from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

from app.config import get_settings
from app.plaid.client import get_plaid_client


def create_link_token(*, user_id: str = "default-user") -> str:
    settings = get_settings()
    client = get_plaid_client()

    kwargs: dict = {
        "products": [Products("transactions")],
        "client_name": "MMM Transactions",
        "country_codes": [CountryCode("US")],
        "language": "en",
        "user": LinkTokenCreateRequestUser(client_user_id=user_id),
        "transactions": {"days_requested": settings.plaid_days_requested},
    }
    if settings.plaid_redirect_uri:
        kwargs["redirect_uri"] = settings.plaid_redirect_uri
    if settings.plaid_webhook_url:
        kwargs["webhook"] = settings.plaid_webhook_url

    response = client.link_token_create(LinkTokenCreateRequest(**kwargs))
    return response.to_dict()["link_token"]


def exchange_public_token(public_token: str) -> dict:
    client = get_plaid_client()
    response = client.item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    )
    return response.to_dict()
