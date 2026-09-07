export type Role = "employee" | "supervisor" | "hr" | "admin";
export type PunchKind = "in" | "out" | "break_start" | "break_end";
export type WorkState = "away" | "in" | "break";

export type User = {
  id: number;
  username: string;
  display_name: string;
  email: string | null;
  role: Role;
  active: boolean;
  work_model_id: number | null;
  work_model_name?: string | null;
  auth_source: string;
  auto_break: boolean;
  transponder_id: string | null;
  web_login: boolean;
  hired_on: string | null;
  left_on: string | null;
};

export type DaySummary = {
  date: string;
  first_in: string | null;
  last_out: string | null;
  work_hours: number;
  break_hours: number;
  soll_hours: number;
  delta_hours: number;
  open: boolean;
  warnings: string[];
  auto_break_minutes: number;
  accepted: { reason: string; at: string } | null;
  absence: { kind: string; note: string | null } | null;
  calendar: { kind: string; name: string; source: string } | null;
  weekday: number;
  punches: { id: number; kind: string; time: string; source: string; voided: boolean }[];
};

export type Status = {
  state: WorkState;
  allowed: PunchKind[];
  since: string | null;
  display_name: string;
  org_name: string;
  server_time: string;
  flex_hours: number;
  total_flex_hours: number;
  recent_days: DaySummary[];
};

export type WorkModelAssignment = {
  id: number;
  work_model_id: number;
  work_model_name: string;
  valid_from: string;
  created_at: string;
};

export type WorkModel = {
  id: number;
  name: string;
  kind: string;
  hours_mon: number;
  hours_tue: number;
  hours_wed: number;
  hours_thu: number;
  hours_fri: number;
  hours_sat: number;
  hours_sun: number;
};

export type FlexBalance = {
  user_id: number;
  work_hours: number;
  soll_hours: number;
  delta_hours: number;
  total_delta_hours: number;
};

export type SmtpSettings = {
  enabled: boolean;
  host: string;
  port: number;
  username: string;
  from_addr: string;
  use_tls: boolean;
  use_ssl: boolean;
  password_set: boolean;
  source: string;
  ready: boolean;
};

export type TerminalDevice = {
  id: number;
  name: string;
  host: string;
  port: number;
  device_address: number;
  enabled: boolean;
  last_poll_at: string | null;
  last_ok_at: string | null;
  last_error: string;
  last_summary: string;
};

export type DfcomSettings = {
  library_ok: boolean;
  library_path: string | null;
  poll_enabled: boolean;
  poll_dry_run: boolean;
  poll_interval_sec: number;
  sync_lists: boolean;
  last_poll: {
    at?: string;
    dry_run?: boolean;
    error?: string;
    devices?: { host: string; read: number; stored: number; preview: number; quit: number; lists_written?: number; error: string }[];
  } | null;
  terminals: TerminalDevice[];
};

export type UserCreateResult = User & {
  mail_sent?: boolean | null;
  mail_error?: string | null;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export const AUTH_EVENT = "ze:unauthorized";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { ...init, headers, credentials: "include", cache: "no-store" });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith("/api/auth/")) {
      window.dispatchEvent(new CustomEvent(AUTH_EVENT, { detail: { path } }));
    }
    const detail =
      typeof data === "object" && data && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : res.statusText;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

export type Meta = {
  org_name: string;
  version: string;
};

export const api = {
  meta: () => request<Meta>("/api/meta"),
  login: (username: string, password: string) =>
    request<User>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  me: () => request<User>("/api/auth/me"),
  forgotPassword: (username_or_email: string) =>
    request<{ ok: boolean }>("/api/auth/forgot", {
      method: "POST",
      body: JSON.stringify({ username_or_email }),
    }),
  passwordTokenInfo: (token: string) =>
    request<{ username: string; display_name: string; purpose: string }>(
      `/api/auth/password-token?token=${encodeURIComponent(token)}`,
    ),
  setPasswordWithToken: (token: string, password: string) =>
    request<{ ok: boolean }>("/api/auth/password-token", {
      method: "POST",
      body: JSON.stringify({ token, password }),
    }),
  changePassword: (current_password: string, new_password: string) =>
    request<{ ok: boolean }>("/api/me/password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),
  status: () => request<Status>("/api/me/status"),
  punch: (kind: PunchKind, clientEventId: string, deviceTime: string) =>
    request("/api/me/punches", {
      method: "POST",
      body: JSON.stringify({
        kind,
        client_event_id: clientEventId,
        device_time: deviceTime,
      }),
    }),
  myDays: (month: string) =>
    request<{ month: string; days: DaySummary[]; month_flex: number; total_flex: number }>(
      `/api/me/days?month=${month}`,
    ),
  users: () => request<User[]>("/api/hr/users"),
  createUser: (body: Record<string, unknown>) =>
    request<UserCreateResult>("/api/hr/users", { method: "POST", body: JSON.stringify(body) }),
  patchUser: (id: number, body: Record<string, unknown>) =>
    request<User>(`/api/hr/users/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  patchUserSettings: (
    id: number,
    body: { auto_break?: boolean; transponder_id?: string | null; web_login?: boolean },
  ) => request<User>(`/api/hr/users/${id}/settings`, { method: "PATCH", body: JSON.stringify(body) }),
  patchUserAccount: (
    id: number,
    body: {
      username?: string;
      display_name?: string;
      email?: string | null;
      role?: string;
      active?: boolean;
      password?: string;
      hired_on?: string | null;
      left_on?: string | null;
    },
  ) => request<User>(`/api/hr/users/${id}/account`, { method: "PATCH", body: JSON.stringify(body) }),
  models: () => request<WorkModel[]>("/api/hr/work-models"),
  createModel: (body: Record<string, unknown>) =>
    request<WorkModel>("/api/hr/work-models", { method: "POST", body: JSON.stringify(body) }),
  userModels: (userId: number) => request<WorkModelAssignment[]>(`/api/hr/users/${userId}/work-models`),
  assignUserModel: (userId: number, body: { work_model_id: number; valid_from: string }) =>
    request<WorkModelAssignment>(`/api/hr/users/${userId}/work-models`, { method: "POST", body: JSON.stringify(body) }),
  deleteUserModel: (userId: number, assignmentId: number) =>
    request(`/api/hr/users/${userId}/work-models/${assignmentId}`, { method: "DELETE" }),
  userDays: (id: number, month: string) =>
    request<{ user: User; month: string; days: DaySummary[]; month_flex: number; total_flex: number }>(
      `/api/hr/users/${id}/days?month=${month}`,
    ),
  replaceDay: (userId: number, day: string, body: { reason: string; punches: { kind: PunchKind; time: string }[] }) =>
    request(`/api/hr/users/${userId}/days/${day}`, { method: "PUT", body: JSON.stringify(body) }),
  acceptDay: (userId: number, day: string, reason: string) =>
    request(`/api/hr/users/${userId}/days/${day}/accept`, { method: "POST", body: JSON.stringify({ reason }) }),
  revokeAccept: (userId: number, day: string) =>
    request(`/api/hr/users/${userId}/days/${day}/accept`, { method: "DELETE" }),
  createAbsences: (userId: number, body: { kind: string; start: string; end: string; note?: string }) =>
    request(`/api/hr/users/${userId}/absences`, { method: "POST", body: JSON.stringify(body) }),
  deleteAbsence: (userId: number, day: string) => request(`/api/hr/users/${userId}/absences/${day}`, { method: "DELETE" }),
  orgSettings: () =>
    request<{ bundesland: string; bundesland_name: string; states: Record<string, string> }>("/api/hr/settings"),
  patchOrgSettings: (body: { bundesland: string }) =>
    request<{ bundesland: string; bundesland_name: string; states: Record<string, string> }>("/api/hr/settings", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  mailStatus: () => request<{ ready: boolean }>("/api/hr/mail-status"),
  smtpSettings: () => request<SmtpSettings>("/api/hr/smtp"),
  patchSmtpSettings: (body: Record<string, unknown>) =>
    request<SmtpSettings>("/api/hr/smtp", { method: "PATCH", body: JSON.stringify(body) }),
  testSmtp: (to?: string) =>
    request<{ ok: boolean }>("/api/hr/smtp/test", { method: "POST", body: JSON.stringify({ to: to || null }) }),
  dfcomSettings: () => request<DfcomSettings>("/api/hr/dfcom"),
  patchDfcomSettings: (body: {
    poll_enabled?: boolean;
    poll_dry_run?: boolean;
    poll_interval_sec?: number;
    sync_lists?: boolean;
  }) => request<DfcomSettings>("/api/hr/dfcom", { method: "PATCH", body: JSON.stringify(body) }),
  pollDfcom: () =>
    request<{ dry_run: boolean; error: string; devices: { host: string; read: number; error: string }[] }>(
      "/api/hr/dfcom/poll",
      { method: "POST" },
    ),
  pushDfcomLists: () =>
    request<{ dry_run: boolean; error: string; devices: { host: string; lists_written?: number; error: string }[] }>(
      "/api/hr/dfcom/lists",
      { method: "POST" },
    ),
  createDfcomTerminal: (body: { name: string; host: string; port: number; device_address?: number; enabled?: boolean }) =>
    request<TerminalDevice>("/api/hr/dfcom/terminals", { method: "POST", body: JSON.stringify(body) }),
  patchDfcomTerminal: (id: number, body: Partial<{ name: string; host: string; port: number; device_address: number; enabled: boolean }>) =>
    request<TerminalDevice>(`/api/hr/dfcom/terminals/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteDfcomTerminal: (id: number) => request<{ ok: boolean }>(`/api/hr/dfcom/terminals/${id}`, { method: "DELETE" }),
  sendAccessMail: (id: number) => request<{ ok: boolean }>(`/api/hr/users/${id}/access-mail`, { method: "POST" }),
  calendar: (year: number) =>
    request<{ id: number | null; day: string; kind: string; name: string; source: string }[]>(
      `/api/hr/calendar?year=${year}`,
    ),
  upsertCalendar: (body: { day: string; kind: string; name: string }) =>
    request(`/api/hr/calendar`, { method: "POST", body: JSON.stringify(body) }),
  deleteCalendar: (id: number) => request(`/api/hr/calendar/${id}`, { method: "DELETE" }),
  plausibility: (month: string) =>
    request<{
      month: string;
      people: {
        user: User;
        model_name: string | null;
        issue_count: number;
        days_with_issues: number;
        counts: Record<string, number>;
        days: { date: string; warnings: string[] }[];
      }[];
    }>(`/api/hr/plausibility?month=${month}`),
  correct: (userId: number, body: Record<string, unknown>) =>
    request(`/api/hr/users/${userId}/corrections`, { method: "POST", body: JSON.stringify(body) }),
  balances: (month: string) =>
    request<{ month: string; people: FlexBalance[] }>(`/api/hr/balances?month=${month}`),
  downloadExportCsv: async (month: string, userId?: number) => {
    const q = new URLSearchParams({ month });
    if (userId) q.set("user_id", String(userId));
    const res = await fetch(`/api/hr/export.csv?${q}`, { credentials: "include", cache: "no-store" });
    if (!res.ok) {
      const text = await res.text();
      let data: unknown = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch {
        data = { detail: text };
      }
      if (res.status === 401) {
        window.dispatchEvent(new CustomEvent(AUTH_EVENT, { detail: { path: "/api/hr/export.csv" } }));
      }
      const detail =
        typeof data === "object" && data && "detail" in data
          ? String((data as { detail: unknown }).detail)
          : res.statusText;
      throw new ApiError(res.status, detail);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `zeiten-${month}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
