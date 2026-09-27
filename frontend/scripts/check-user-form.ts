import assert from "node:assert/strict";
import { firstUserFieldError, validEmail, validateUserAccount } from "../src/userForm.ts";

assert.equal(validEmail("a@example.com"), true);
assert.equal(validEmail("no-at"), false);
assert.equal(validEmail("a@localhost"), true);

const empty = validateUserAccount({
  first_name: "  ",
  last_name: "  ",
  username: "",
  email: "",
  emailRequired: true,
  password: "",
  passwordRequired: true,
  hired_on: "",
  left_on: "",
});
assert.equal(empty.last_name, "Name fehlt.");
assert.equal(empty.username, "Benutzername fehlt.");
assert.equal(empty.email, "E-Mail-Adresse fehlt.");
assert.equal(empty.password, "Passwort für die Web-Anmeldung fehlt.");
assert.equal(empty.hired_on, "Eintrittsdatum fehlt.");
assert.equal(firstUserFieldError(empty), "Name fehlt.");

const dates = validateUserAccount({
  first_name: "Erika",
  last_name: "Schicht",
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
  first_name: "Erika",
  last_name: "",
  username: "erika",
  email: "",
  password: "",
  hired_on: "2026-09-10",
  left_on: "",
});
assert.equal(firstUserFieldError(ok), undefined);

console.log("userForm ok");
