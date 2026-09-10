from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (
    AttestationConveyancePreference,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialCreationOptions,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialRequestOptions,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.config import get_config
from app.models import WebAuthnCredential

_DEV_HOSTS = {"localhost", "127.0.0.1"}


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def resolve_rp(request: Request) -> tuple[str, list[str]]:
    """Return (rp_id, expected_origins) for the current request.

    Production uses the configured rp_id / origins (derived from public_url when
    unset). In development we additionally trust a localhost/127.0.0.1 request
    origin so passkeys work on the Vite dev server without extra config.
    """
    cfg = get_config()
    wc = cfg.webauthn
    origins: list[str] = [o.rstrip("/") for o in wc.origins if o.strip()]
    if not origins and cfg.public_url:
        origins = [cfg.public_url.rstrip("/")]

    req_origin = (request.headers.get("origin") or "").rstrip("/")
    req_host = _host(req_origin)
    if cfg.is_dev and req_origin and req_host in _DEV_HOSTS and req_origin not in origins:
        origins.append(req_origin)

    if wc.rp_id:
        rp_id = wc.rp_id
    elif cfg.is_dev and req_host in _DEV_HOSTS:
        rp_id = req_host
    else:
        rp_id = _host(cfg.public_url) or "localhost"
    return rp_id, origins


def _rp_name() -> str:
    return get_config().org_name or "Opentakt Zeit"


def _descriptors(creds: list[WebAuthnCredential]) -> list[PublicKeyCredentialDescriptor]:
    return [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in creds]


def registration_options(
    request: Request, user_id: int, username: str, display_name: str, existing: list[WebAuthnCredential]
) -> tuple[PublicKeyCredentialCreationOptions, str]:
    rp_id, _ = resolve_rp(request)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=_rp_name(),
        user_name=username,
        user_id=str(user_id).encode("utf-8"),
        user_display_name=display_name,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=_descriptors(existing),
    )
    return options, rp_id


def verify_registration(request: Request, credential: dict, expected_challenge: str) -> tuple[str, str, int, str]:
    """Verify an attestation and return (credential_id, public_key, sign_count, rp_id)."""
    rp_id, origins = resolve_rp(request)
    result = verify_registration_response(
        credential=credential,
        expected_challenge=base64url_to_bytes(expected_challenge),
        expected_rp_id=rp_id,
        expected_origin=origins,
        require_user_verification=False,
    )
    return (
        bytes_to_base64url(result.credential_id),
        bytes_to_base64url(result.credential_public_key),
        int(result.sign_count),
        rp_id,
    )


def authentication_options(
    request: Request, creds: list[WebAuthnCredential]
) -> tuple[PublicKeyCredentialRequestOptions, str]:
    rp_id, _ = resolve_rp(request)
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=_descriptors(creds) or None,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return options, rp_id


def verify_authentication(
    request: Request, credential: dict, expected_challenge: str, cred: WebAuthnCredential
) -> int:
    """Verify an assertion against a stored credential and return the new sign count."""
    rp_id, origins = resolve_rp(request)
    result = verify_authentication_response(
        credential=credential,
        expected_challenge=base64url_to_bytes(expected_challenge),
        expected_rp_id=rp_id,
        expected_origin=origins,
        credential_public_key=base64url_to_bytes(cred.public_key),
        credential_current_sign_count=cred.sign_count,
        require_user_verification=False,
    )
    return int(result.new_sign_count)


def credential_raw_id(credential: dict) -> str:
    raw = credential.get("rawId") or credential.get("id") or ""
    return str(raw)
