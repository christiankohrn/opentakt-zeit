from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_config
from app.models import User
from app.security import hash_password


def try_ldap_login(db: Session, username: str, password: str, existing: User | None) -> User | None:
    """Bind against AD/LDAP. Disabled unless config.ldap.enabled is true."""
    cfg = get_config().ldap
    if not cfg.enabled or not cfg.url:
        return None
    try:
        from ldap3 import ALL, Connection, Server
    except ImportError:
        return None

    server = Server(cfg.url, get_info=ALL, connect_timeout=5)
    user_filter = cfg.user_filter.format(username=username)
    bind_kwargs = {}
    if cfg.bind_dn:
        bind_kwargs = {"user": cfg.bind_dn, "password": cfg.bind_password}
    conn = Connection(server, auto_bind=True, **bind_kwargs)
    conn.search(cfg.user_base, user_filter, attributes=["displayName", "mail", "distinguishedName"])
    if not conn.entries:
        conn.unbind()
        return None
    entry = conn.entries[0]
    dn = str(entry.distinguishedName)
    conn.unbind()
    check = Connection(server, user=dn, password=password, auto_bind=False)
    if not check.bind():
        return None
    check.unbind()

    display = str(entry.displayName) if "displayName" in entry else username
    email = str(entry.mail) if "mail" in entry else None
    if existing:
        if not existing.active:
            return None
        existing.display_name = display or existing.display_name
        existing.email = email or existing.email
        existing.auth_source = "ldap"
        db.commit()
        return existing
    user = User(
        username=username,
        display_name=display or username,
        email=email,
        password_hash=None,
        auth_source="ldap",
        role="employee",
        active=True,
    )
    # local users still need a dummy hash never used
    user.password_hash = hash_password("ldap-no-local-login")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
