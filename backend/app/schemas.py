from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    email: Optional[str]
    role: str
    active: bool
    work_model_id: Optional[int]
    work_model_name: Optional[str] = None
    auth_source: str
    auto_break: bool = False
    transponder_id: Optional[str] = None
    web_login: bool = True
    hired_on: Optional[date] = None
    left_on: Optional[date] = None
    totp_enabled: bool = False
    passkey_count: int = 0
    security_setup_required: Optional[str] = None

    model_config = {"from_attributes": True}


class WorkModelAssignIn(BaseModel):
    work_model_id: int
    valid_from: date


class WorkModelAssignOut(BaseModel):
    id: int
    work_model_id: int
    work_model_name: str
    valid_from: date
    created_at: datetime

    model_config = {"from_attributes": True}


class PunchIn(BaseModel):
    kind: Literal["in", "out", "break_start", "break_end"]
    client_event_id: str = Field(min_length=8, max_length=64)
    device_time: Optional[datetime] = None
    note: Optional[str] = None


class PunchOut(BaseModel):
    id: int
    kind: str
    server_time: datetime
    source: str
    client_event_id: Optional[str]

    model_config = {"from_attributes": True}


class StatusOut(BaseModel):
    state: str
    allowed: list[str]
    since: Optional[datetime] = None
    display_name: str
    org_name: str
    server_time: datetime
    flex_hours: float = 0
    total_flex_hours: float = 0
    recent_days: list[dict] = Field(default_factory=list)


class WorkModelIn(BaseModel):
    name: str
    kind: str = "flextime"
    hours_mon: float = 8
    hours_tue: float = 8
    hours_wed: float = 8
    hours_thu: float = 8
    hours_fri: float = 8
    hours_sat: float = 0
    hours_sun: float = 0


class WorkModelOut(WorkModelIn):
    id: int
    model_config = {"from_attributes": True}


class UserWrite(BaseModel):
    username: str
    display_name: str
    email: Optional[str] = None
    password: Optional[str] = None
    role: str = "employee"
    active: bool = True
    work_model_id: Optional[int] = None
    auto_break: bool = False
    transponder_id: Optional[str] = None
    web_login: bool = True
    hired_on: Optional[date] = None
    left_on: Optional[date] = None
    send_access_mail: bool = False


class UserCreateOut(UserOut):
    mail_sent: Optional[bool] = None
    mail_error: Optional[str] = None


class CorrectionIn(BaseModel):
    punch_id: Optional[int] = None
    kind: Literal["in", "out", "break_start", "break_end"]
    local_time: datetime
    reason: str = Field(min_length=3, max_length=300)


class DayPunchDraft(BaseModel):
    kind: Literal["in", "out", "break_start", "break_end"]
    time: str = Field(pattern=r"^\d{2}:\d{2}$")


class DayReplaceIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)
    punches: list[DayPunchDraft]


class DayAcceptIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class AbsenceRangeIn(BaseModel):
    kind: Literal["vacation", "sick", "holiday"]
    start: date
    end: date
    note: Optional[str] = None


class UserSettingsIn(BaseModel):
    auto_break: Optional[bool] = None
    transponder_id: Optional[str] = None
    web_login: Optional[bool] = None


class UserAccountIn(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)
    hired_on: Optional[date] = None
    left_on: Optional[date] = None


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


class ForgotIn(BaseModel):
    username_or_email: str = Field(min_length=1, max_length=200)


class ResetIn(BaseModel):
    token: str = Field(min_length=8, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class ResetInfoOut(BaseModel):
    username: str
    display_name: str
    purpose: str


class MfaRequiredOut(BaseModel):
    mfa_required: bool = True
    methods: list[str] = Field(default_factory=list)


class MfaVerifyIn(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg: str


class TotpEnableIn(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class TotpEnableOut(BaseModel):
    backup_codes: list[str]


class TotpDisableIn(BaseModel):
    password: Optional[str] = None
    code: Optional[str] = None


class PasskeyOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    last_used_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SecurityStatusOut(BaseModel):
    totp_enabled: bool
    backup_codes_remaining: int
    can_use_password: bool
    passkeys: list[PasskeyOut] = Field(default_factory=list)


class PasskeyRegisterVerifyIn(BaseModel):
    credential: dict
    name: Optional[str] = Field(default=None, max_length=120)


class PasskeyRenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PasskeyAuthOptionsIn(BaseModel):
    username: Optional[str] = Field(default=None, max_length=200)


class PasskeyAuthVerifyIn(BaseModel):
    credential: dict


class SmtpSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    from_addr: Optional[str] = None
    use_tls: Optional[bool] = None
    use_ssl: Optional[bool] = None


class SmtpTestIn(BaseModel):
    to: Optional[str] = None


class OrgSettingsOut(BaseModel):
    bundesland: str
    bundesland_name: str
    states: dict[str, str]


class OrgSettingsIn(BaseModel):
    bundesland: str


class SecurityPolicyOut(BaseModel):
    policies: dict[str, str]
    roles: list[str]
    values: list[str]


class SecurityPolicyIn(BaseModel):
    policies: dict[str, str]


class EspPunchIn(BaseModel):
    badge: str = Field(min_length=1, max_length=80)
    event_id: str = Field(min_length=8, max_length=64)
    device_id: str = Field(default="", max_length=80)


class EspPunchOut(BaseModel):
    ok: bool
    line1: str
    line2: str
    kind: Optional[str] = None


class EspTerminalSettingsIn(BaseModel):
    ok_line1: Optional[str] = Field(default=None, max_length=80)
    ok_line2: Optional[str] = Field(default=None, max_length=80)


class EspTerminalSettingsOut(BaseModel):
    secret_configured: bool
    ok_line1: str
    ok_line2: str
    placeholders: list[str] = Field(
        default_factory=lambda: ["first_name", "display_name", "kind", "flex_month", "flex_total"]
    )


class TerminalDeviceIn(BaseModel):
    name: str = Field(default="Terminal", max_length=120)
    host: str = Field(min_length=1, max_length=200)
    port: int = Field(default=8000, ge=1, le=65535)
    device_address: int = Field(default=255, ge=0, le=255)
    enabled: bool = True


class TerminalDevicePatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    host: Optional[str] = Field(default=None, max_length=200)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    device_address: Optional[int] = Field(default=None, ge=0, le=255)
    enabled: Optional[bool] = None


class TerminalDeviceOut(BaseModel):
    id: int
    name: str
    host: str
    port: int
    device_address: int
    enabled: bool
    last_poll_at: Optional[datetime] = None
    last_ok_at: Optional[datetime] = None
    last_error: str = ""
    last_summary: str = ""

    model_config = {"from_attributes": True}


class DfcomSettingsIn(BaseModel):
    poll_enabled: Optional[bool] = None
    poll_dry_run: Optional[bool] = None
    poll_interval_sec: Optional[int] = Field(default=None, ge=10, le=300)
    sync_lists: Optional[bool] = None


class DfcomSettingsOut(BaseModel):
    library_ok: bool
    library_path: Optional[str] = None
    poll_enabled: bool
    poll_dry_run: bool
    poll_interval_sec: int
    sync_lists: bool
    last_poll: Optional[dict] = None
    terminals: list[TerminalDeviceOut] = Field(default_factory=list)


class CalendarIn(BaseModel):
    day: date
    kind: Literal["holiday", "company_off"]
    name: str = Field(min_length=2, max_length=160)


class CalendarOut(BaseModel):
    id: int | None = None
    day: date
    kind: str
    name: str
    source: str
