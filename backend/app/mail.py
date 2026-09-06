from __future__ import annotations

import hashlib
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import now_utc
from app.branding import PRODUCT_NAME
from app.config import SmtpConfig, get_config
from app.models import MailToken, OrgSettings, User

INVITE_DAYS = 7
RESET_HOURS = 1
RESET_RESEND_MINUTES = 10


class MailError(Exception):
    pass


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def valid_email(value: str | None) -> bool:
    email = normalize_email(value)
    if not email or " " in email or email.count("@") != 1:
        return False
    local, domain = email.split("@", 1)
    if not local or not domain or domain.startswith(".") or domain.endswith("."):
        return False
    return domain == "localhost" or "." in domain


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt


def _row_smtp(row: OrgSettings) -> SmtpConfig:
    return SmtpConfig(
        enabled=bool(row.smtp_enabled),
        host=(row.smtp_host or "").strip(),
        port=int(row.smtp_port or 587),
        username=(row.smtp_username or "").strip(),
        password=row.smtp_password or "",
        from_addr=(row.smtp_from or "").strip(),
        use_tls=bool(row.smtp_use_tls),
        use_ssl=bool(row.smtp_use_ssl),
    )


def effective_smtp(db: Session | None = None) -> SmtpConfig:
    cfg = get_config().smtp
    if db is None:
        from app.database import SessionLocal

        local = SessionLocal()
        try:
            return effective_smtp(local)
        finally:
            local.close()
    row = db.get(OrgSettings, 1)
    if row and row.smtp_configured:
        return _row_smtp(row)
    return cfg


def smtp_public(smtp: SmtpConfig, *, source: str) -> dict:
    return {
        "enabled": smtp.enabled,
        "host": smtp.host,
        "port": smtp.port,
        "username": smtp.username,
        "from_addr": smtp.from_addr,
        "use_tls": smtp.use_tls,
        "use_ssl": smtp.use_ssl,
        "password_set": bool(smtp.password),
        "source": source,
        "ready": smtp_ready_config(smtp),
    }


def smtp_status(db: Session) -> dict:
    row = db.get(OrgSettings, 1)
    source = "db" if row and row.smtp_configured else "config"
    smtp = effective_smtp(db)
    return smtp_public(smtp, source=source)


def smtp_ready_config(smtp: SmtpConfig) -> bool:
    return bool(smtp.enabled and smtp.host and smtp.from_addr)


def smtp_ready(db: Session | None = None) -> bool:
    return smtp_ready_config(effective_smtp(db))


def apply_smtp(db: Session, payload: dict) -> SmtpConfig:
    row = db.get(OrgSettings, 1)
    if row is None:
        row = OrgSettings(id=1, bundesland=(get_config().bundesland or "NW").upper())
        db.add(row)
        db.flush()
    current = effective_smtp(db)
    base = _row_smtp(row) if row.smtp_configured else current
    row.smtp_configured = True
    row.smtp_enabled = bool(payload["enabled"]) if payload.get("enabled") is not None else base.enabled
    if payload.get("host") is not None:
        row.smtp_host = str(payload["host"]).strip()
    elif not row.smtp_host:
        row.smtp_host = base.host
    if payload.get("port") is not None:
        port = int(payload["port"])
        if port < 1 or port > 65535:
            raise MailError("Ungültiger Port")
        row.smtp_port = port
    elif not row.smtp_port:
        row.smtp_port = base.port
    if payload.get("username") is not None:
        row.smtp_username = str(payload["username"]).strip()
    elif not row.smtp_username:
        row.smtp_username = base.username
    if payload.get("from_addr") is not None:
        addr = str(payload["from_addr"]).strip()
        if addr and not valid_email(addr):
            raise MailError("Absenderadresse ist ungültig")
        row.smtp_from = addr
    elif not row.smtp_from:
        row.smtp_from = base.from_addr
    if payload.get("use_tls") is not None:
        row.smtp_use_tls = bool(payload["use_tls"])
    if payload.get("use_ssl") is not None:
        row.smtp_use_ssl = bool(payload["use_ssl"])
    password = payload.get("password")
    if password:
        row.smtp_password = str(password)
    elif not row.smtp_password:
        row.smtp_password = base.password
    db.flush()
    return _row_smtp(row)


def deliver_message(smtp: SmtpConfig, msg: EmailMessage) -> None:
    use_ssl = smtp.use_ssl or smtp.port == 465
    if use_ssl:
        context = ssl.create_default_context()
        client: smtplib.SMTP = smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=20, context=context)
    else:
        client = smtplib.SMTP(smtp.host, smtp.port, timeout=20)
    with client:
        if not use_ssl and smtp.use_tls:
            client.starttls(context=ssl.create_default_context())
        if smtp.username:
            client.login(smtp.username, smtp.password)
        client.send_message(msg)


def send_mail(to: str, subject: str, body: str, *, db: Session | None = None, required: bool = True) -> bool:
    smtp = effective_smtp(db)
    if not smtp_ready_config(smtp):
        if required:
            raise MailError("Mailserver ist nicht eingerichtet")
        print(f"[mail-disabled] to={to} subject={subject}\n{body}")
        return False
    msg = EmailMessage()
    msg["From"] = smtp.from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        deliver_message(smtp, msg)
    except (OSError, smtplib.SMTPException) as exc:
        if required:
            raise MailError(f"Mailversand fehlgeschlagen: {exc}") from exc
        print(f"[mail-error] to={to} subject={subject} err={exc}")
        return False
    return True


def create_mail_token(db: Session, user: User, purpose: str) -> str:
    now = now_utc()
    old = list(
        db.scalars(
            select(MailToken).where(
                MailToken.user_id == user.id,
                MailToken.purpose == purpose,
                MailToken.used_at.is_(None),
            )
        )
    )
    for row in old:
        db.delete(row)
    raw = secrets.token_urlsafe(32)
    ttl = timedelta(days=INVITE_DAYS) if purpose == "invite" else timedelta(hours=RESET_HOURS)
    db.add(
        MailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=now + ttl,
            created_at=now,
        )
    )
    db.flush()
    return raw


def lookup_mail_token(db: Session, raw: str) -> MailToken | None:
    token = (raw or "").strip()
    if not token or len(token) > 200:
        return None
    row = db.scalar(select(MailToken).where(MailToken.token_hash == hash_token(token)))
    if not row or row.used_at is not None:
        return None
    if _aware(row.expires_at) <= now_utc():
        return None
    return row


def has_open_invite(db: Session, user: User) -> bool:
    now = now_utc()
    row = db.scalar(
        select(MailToken).where(
            MailToken.user_id == user.id,
            MailToken.purpose == "invite",
            MailToken.used_at.is_(None),
        )
    )
    return bool(row and _aware(row.expires_at) > now)


def recent_unused_token(db: Session, user: User, purpose: str, within: timedelta) -> MailToken | None:
    now = now_utc()
    rows = list(
        db.scalars(
            select(MailToken).where(
                MailToken.user_id == user.id,
                MailToken.purpose == purpose,
                MailToken.used_at.is_(None),
            )
        )
    )
    for row in rows:
        if now - _aware(row.created_at) < within:
            return row
    return None


def access_url(token: str) -> str:
    base = get_config().public_url.rstrip("/")
    return f"{base}/passwort-setzen?token={token}"


def _login_url() -> str:
    return get_config().public_url.rstrip("/")


def invite_mail_body(user: User, token: str) -> str:
    cfg = get_config()
    return (
        f"Hallo {user.display_name},\n\n"
        f"für dich wurde ein Zugang zu {PRODUCT_NAME} von {cfg.org_name} eingerichtet.\n\n"
        f"Benutzername: {user.username}\n"
        f"Anmeldung: {_login_url()}\n\n"
        f"Bitte setze dein Passwort über diesen Link (gültig {INVITE_DAYS} Tage):\n"
        f"{access_url(token)}\n\n"
        "Falls du diese Mail nicht erwartet hast, kannst du sie ignorieren.\n"
    )


def reset_mail_body(user: User, token: str) -> str:
    cfg = get_config()
    return (
        f"Hallo {user.display_name},\n\n"
        f"für dein Konto {user.username} bei {cfg.org_name} wurde ein neues Passwort angefordert.\n\n"
        f"Link zum Setzen (gültig {RESET_HOURS} Stunde):\n"
        f"{access_url(token)}\n\n"
        "Wenn du das nicht warst, ignoriere die Mail. Dein bisheriges Passwort bleibt gültig.\n"
    )


def send_access_mail(db: Session, user: User, *, purpose: str) -> None:
    email = normalize_email(user.email)
    if not valid_email(email):
        raise MailError("Gültige E-Mail-Adresse erforderlich")
    if user.auth_source != "local":
        raise MailError("Passwort wird im Benutzerverzeichnis geändert")
    if not user.web_login:
        raise MailError("Keine Web-Anmeldung für diesen Benutzer")
    if not user.active:
        raise MailError("Benutzer ist inaktiv")
    if not smtp_ready(db):
        raise MailError("Mailserver ist nicht eingerichtet")
    token = create_mail_token(db, user, purpose)
    cfg = get_config()
    if purpose == "reset":
        subject = f"{cfg.org_name}: Passwort zurücksetzen"
        body = reset_mail_body(user, token)
    else:
        subject = f"{cfg.org_name}: Zugang zu {PRODUCT_NAME}"
        body = invite_mail_body(user, token)
    send_mail(email, subject, body, db=db, required=True)


def send_test_mail(db: Session, to: str) -> None:
    email = normalize_email(to)
    if not valid_email(email):
        raise MailError("Gültige E-Mail-Adresse erforderlich")
    cfg = get_config()
    send_mail(
        email,
        f"{cfg.org_name}: Testmail",
        f"Dies ist eine Testmail von {PRODUCT_NAME} ({cfg.org_name}).\n"
        "Der Mailserver ist erreichbar.\n",
        db=db,
        required=True,
    )


def find_local_user(db: Session, username_or_email: str) -> User | None:
    key = username_or_email.strip()
    if not key:
        return None
    from sqlalchemy import func

    from app.auth import normalize_username

    user = db.scalar(select(User).where(func.lower(User.username) == normalize_username(key)))
    if user:
        return user
    email = normalize_email(key)
    if not email:
        return None
    return db.scalar(select(User).where(func.lower(User.email) == email))
