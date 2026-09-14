"""Deterministic External ID derivation for cross-account AssumeRole.

The External ID mitigates the confused-deputy problem for third-party/SaaS
cross-account access. We derive it from the tenant + connection identifiers
using an HMAC keyed by a server-side secret. This makes it:

- stable/reproducible (the wizard can show the same value the trust policy
  must contain), and
- unguessable without the server secret.

It is connection metadata, not an AWS credential. It is safe to show to the
owning tenant, but must never be exposed across tenants.
"""
from __future__ import annotations

import hashlib
import hmac

from app.core.config import get_settings


def derive_external_id(tenant_id: str, connection_id: str) -> str:
    """Return a stable External ID for a (tenant, connection) pair."""
    settings = get_settings()
    message = f"{tenant_id}:{connection_id}".encode()
    digest = hmac.new(
        settings.external_id_secret.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()
    # A compact, readable token. 32 hex chars is ample entropy for an ExternalId.
    return f"ccc-{digest[:32]}"
