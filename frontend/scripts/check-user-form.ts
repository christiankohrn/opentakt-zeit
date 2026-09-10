import assert from "node:assert/strict";
import { firstUserFieldError, validEmail, validateUserAccount } from "../src/userForm.ts";

assert.equal(validEmail("a@example.com"), true);
assert.equal(validEmail("no-at"), false);
assert.equal(validEmail("a@localhost"), true);

const empty = validateUserAccount({
  display_name: "  ",
  username: "",
  email: "",
  emailRequired: true,
  password: "",
  passwordRequired: true,
  hired_on: "",
  left_on: "",
});
assert.equal(empty.display_name, "Anzeigename fehlt.");
assert.equal(empty.username, "Benutzername fehlt.");
assert.equal(empty.email, "E-Mail-Adresse fehlt.");
assert.equal(empty.password, "Passwort für die Web-Anmeldung fehlt.");
assert.equal(empty.hired_on, "Eintrittsdatum fehlt.");
assert.equal(firstUserFieldError(empty), "Anzeigename fehlt.");

const dates = validateUserAccount({
  display_name: "Erika",
  username: "erika",
  email: "bad",
  password: "short",
  hired_on: "2026-09-10",
  left_on: "2026-09-01",
});
assert.equal(dates.email, "E-Mail-Adresse ist ungültig.");
assert.equal(dates.password, "Mindestens 8 Zeichen.");
assert.equal(dates.left_on, "Austritt liegt vor dem Eintritt.");

const ok = validateUserAccount({
  display_name: "Erika",
  username: "erika",
  email: "",
  password: "",
  hired_on: "2026-09-10",
  left_on: "",
});
assert.equal(firstUserFieldError(ok), undefined);

console.log("userForm ok");
