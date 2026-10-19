"""Credentials and settings for the services that run on Azure.

In Azure each container app runs as its own user-assigned managed identity, named by AZURE_CLIENT_ID.
Locally the services fall back to the developer's Azure CLI sign-in, which `azd provision` grants the
same data-plane roles. No service uses a key or a connection string.
"""

from __future__ import annotations

import os

from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential


def credential() -> AsyncTokenCredential:
    client_id = os.environ.get("AZURE_CLIENT_ID")
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)
    return AzureCliCredential()


def require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"environment variable {name} is not set")
    return value
