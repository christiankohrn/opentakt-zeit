from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WorkModel(Base):
    __tablename__ = "work_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(32), default="flextime")
    hours_mon: Mapped[float] = mapped_column(Float, default=8.0)
    hours_tue: Mapped[float] = mapped_column(Float, default=8.0)
    hours_wed: Mapped[float] = mapped_column(Float, default=8.0)
    hours_thu: Mapped[float] = mapped_column(Float, default=8.0)
    hours_fri: Mapped[float] = mapped_column(Float, default=8.0)
    hours_sat: Mapped[float] = mapped_column(Float, default=0.0)
    hours_sun: Mapped[float] = mapped_column(Float, default=0.0)
    core_start: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    core_end: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="work_model")
    assignments: Mapped[list["WorkModelAssignment"]] = relationship(back_populates="work_model")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    auth_source: Mapped[str] = mapped_column(String(16), default="local")
    role: Mapped[str] = mapped_column(String(32), default="employee")
    active: Mapped[bool] = mapped_column(default=True)
    work_model_id: Mapped[Optional[int]] = mapped_column(ForeignKey("work_models.id"), nullable=True)
    auto_break: Mapped[bool] = mapped_column(default=False)
    transponder_id: Mapped[Optional[str]] = mapped_column(String(80), unique=True, nullable=True)
    web_login: Mapped[bool] = mapped_column(default=True)
    hired_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    left_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    session_rev: Mapped[int] = mapped_column(Integer, default=0)
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(default=False)
    totp_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    work_model: Mapped[Optional[WorkModel]] = relationship(back_populates="users")
    model_assignments: Mapped[list["WorkModelAssignment"]] = relationship(
        back_populates="user",
        foreign_keys="WorkModelAssignment.user_id",
    )
    punches: Mapped[list["Punch"]] = relationship(
        back_populates="user",
        foreign_keys="Punch.user_id",
    )


class WorkModelAssignment(Base):
    __tablename__ = "work_model_assignments"
    __table_args__ = (UniqueConstraint("user_id", "valid_from", name="uq_work_model_assignment_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    work_model_id: Mapped[int] = mapped_column(ForeignKey("work_models.id"), index=True)
    valid_from: Mapped[date] = mapped_column(Date, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="model_assignments", foreign_keys=[user_id])
    work_model: Mapped[WorkModel] = relationship(back_populates="assignments")


class Punch(Base):
    __tablename__ = "punches"
    __table_args__ = (UniqueConstraint("user_id", "client_event_id", name="uq_punch_client_event"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # in, out, break_start, break_end
    server_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    device_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="pwa")
    client_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    terminal_name: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    void_reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    replaces_id: Mapped[Optional[int]] = mapped_column(ForeignKey("punches.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="punches", foreign_keys=[user_id])


class Absence(Base):
    __tablename__ = "absences"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_absence_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(32))  # vacation, sick, holiday, other
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class DayAcceptance(Base):
    __tablename__ = "day_acceptances"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_day_acceptance"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    reason: Mapped[str] = mapped_column(String(300))
    warnings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    accepted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class CalendarEntry(Base):
    __tablename__ = "calendar_days"
    __table_args__ = (UniqueConstraint("day", name="uq_calendar_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(32))  # holiday, company_off
    name: Mapped[str] = mapped_column(String(160))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class OrgSettings(Base):
    __tablename__ = "org_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bundesland: Mapped[str] = mapped_column(String(8), default="NW")
    smtp_configured: Mapped[bool] = mapped_column(default=False)
    smtp_enabled: Mapped[bool] = mapped_column(default=False)
    smtp_host: Mapped[str] = mapped_column(String(200), default="")
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_username: Mapped[str] = mapped_column(String(200), default="")
    smtp_password: Mapped[str] = mapped_column(String(400), default="")
    smtp_from: Mapped[str] = mapped_column(String(200), default="")
    smtp_use_tls: Mapped[bool] = mapped_column(default=True)
    smtp_use_ssl: Mapped[bool] = mapped_column(default=False)
    # Erzwungene starke Anmeldung je Rolle: off | totp | passkey | any
    mfa_policy_employee: Mapped[str] = mapped_column(String(16), default="off")
    mfa_policy_supervisor: Mapped[str] = mapped_column(String(16), default="off")
    mfa_policy_hr: Mapped[str] = mapped_column(String(16), default="off")
    mfa_policy_admin: Mapped[str] = mapped_column(String(16), default="off")
    dfcom_poll_enabled: Mapped[bool] = mapped_column(default=False)
    dfcom_poll_dry_run: Mapped[bool] = mapped_column(default=True)
    dfcom_poll_interval_sec: Mapped[int] = mapped_column(Integer, default=20)
    dfcom_sync_lists: Mapped[bool] = mapped_column(default=True)
    dfcom_last_poll: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    esp_ok_line1: Mapped[str] = mapped_column(String(80), default="{first_name}")
    esp_ok_line2: Mapped[str] = mapped_column(String(80), default="{kind} {flex_month}")
    esp_terminal_secret: Mapped[str] = mapped_column(String(200), default="")
    esp_firmware_version: Mapped[int] = mapped_column(Integer, default=0)


class EspTerminal(Base):
    __tablename__ = "esp_terminals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    firmware: Mapped[int] = mapped_column(Integer, default=0)
    last_ssid: Mapped[str] = mapped_column(String(80), default="")
    last_ip: Mapped[str] = mapped_column(String(64), default="")
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    wifi_ssid: Mapped[str] = mapped_column(String(80), default="")
    wifi_pass: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class TerminalDevice(Base):
    __tablename__ = "terminal_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="Terminal")
    host: Mapped[str] = mapped_column(String(200))
    port: Mapped[int] = mapped_column(Integer, default=8000)
    device_address: Mapped[int] = mapped_column(Integer, default=255)
    enabled: Mapped[bool] = mapped_column(default=True)
    last_poll_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ok_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(400), default="")
    last_summary: Mapped[str] = mapped_column(String(500), default="")
    last_list_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class MailToken(Base):
    __tablename__ = "mail_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(16), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    user: Mapped[User] = relationship()


class TotpBackupCode(Base):
    __tablename__ = "totp_backup_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(200))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    user: Mapped[User] = relationship()


class WebAuthnCredential(Base):
    __tablename__ = "webauthn_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    credential_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    transports: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    name: Mapped[str] = mapped_column(String(120), default="Passkey")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
