export type UserFieldErrors = {
  display_name?: string;
  username?: string;
  email?: string;
  password?: string;
  hired_on?: string;
  left_on?: string;
};

export function validEmail(value: string): boolean {
  const email = value.trim().toLowerCase();
  if (!email || email.includes(" ") || email.split("@").length !== 2) return false;
  const [local, domain] = email.split("@");
  if (!local || !domain || domain.startsWith(".") || domain.endsWith(".")) return false;
  return domain === "localhost" || domain.includes(".");
}

export function validateUserAccount(input: {
  display_name: string;
  username: string;
  email: string;
  emailRequired?: boolean;
  password: string;
  passwordRequired?: boolean;
  hired_on: string;
  left_on: string;
}): UserFieldErrors {
  const errors: UserFieldErrors = {};
  if (!input.display_name.trim()) errors.display_name = "Anzeigename fehlt.";
  if (!input.username.trim()) errors.username = "Benutzername fehlt.";
  if (input.emailRequired && !input.email.trim()) errors.email = "E-Mail-Adresse fehlt.";
  else if (input.email.trim() && !validEmail(input.email)) errors.email = "E-Mail-Adresse ist ungültig.";
  if (input.passwordRequired && !input.password) errors.password = "Passwort für die Web-Anmeldung fehlt.";
  else if (input.password && input.password.length < 8) errors.password = "Mindestens 8 Zeichen.";
  if (!input.hired_on) errors.hired_on = "Eintrittsdatum fehlt.";
  if (input.hired_on && input.left_on && input.left_on < input.hired_on) {
    errors.left_on = "Austritt liegt vor dem Eintritt.";
  }
  return errors;
}

export function firstUserFieldError(errors: UserFieldErrors): string | undefined {
  return (
    errors.display_name ||
    errors.username ||
    errors.email ||
    errors.password ||
    errors.hired_on ||
    errors.left_on
  );
}

export function inputClass(error: string | undefined, extra = "") {
  return `rounded-lg border bg-bg text-ink ${error ? "border-danger" : "border-line"} ${extra}`.replace(/\s+/g, " ").trim();
}
