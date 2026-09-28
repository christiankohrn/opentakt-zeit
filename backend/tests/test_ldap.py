from __future__ import annotations


def test_username_is_escaped_in_ldap_filter(monkeypatch):
    import ldap3

    from app.config import LdapConfig, get_config
    from app.database import SessionLocal
    from app.ldap_auth import try_ldap_login

    cfg = get_config()
    ldap_cfg = LdapConfig(
        enabled=True,
        url="ldap://directory.test",
        user_base="ou=users,dc=test",
        user_filter="(uid={username})",
    )
    monkeypatch.setattr("app.ldap_auth.get_config", lambda: cfg.model_copy(update={"ldap": ldap_cfg}))
    monkeypatch.setattr(ldap3, "Server", lambda *args, **kwargs: object())

    seen: dict = {}

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            self.entries: list = []

        def search(self, base, search_filter, attributes=None):
            seen["filter"] = search_filter

        def unbind(self):
            pass

    monkeypatch.setattr(ldap3, "Connection", FakeConnection)

    db = SessionLocal()
    try:
        assert try_ldap_login(db, "a*)(uid=*", "pw", None) is None
    finally:
        db.close()
    assert seen["filter"] == "(uid=a\\2a\\29\\28uid=\\2a)"
