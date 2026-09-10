import { Navigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import AuthScreen from "../components/AuthScreen";
import SecuritySettings from "../components/SecuritySettings";

const HINTS: Record<string, string> = {
  totp: "Für dein Konto ist Zwei-Faktor per Authenticator-App vorgeschrieben. Bitte richte sie jetzt ein.",
  passkey: "Für dein Konto ist ein Passkey vorgeschrieben. Bitte lege jetzt einen an.",
  any: "Für dein Konto ist eine zweite Sicherheitsstufe vorgeschrieben. Richte 2FA oder einen Passkey ein — eines genügt.",
};

export default function SecuritySetup() {
  const { user, loading, refresh, setUser } = useAuth();

  if (loading) return <div className="p-8 text-muted">Laden …</div>;
  if (!user) return <Navigate to="/login" replace />;

  const required = user.security_setup_required;
  if (!required) return <Navigate to="/" replace />;

  const restrict = (["totp", "passkey", "any"].includes(required) ? required : "any") as "totp" | "passkey" | "any";

  async function onLogout() {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }

  return (
    <AuthScreen
      title="Sicherheit einrichten."
      lead={HINTS[required] ?? HINTS.any}
    >
      <SecuritySettings restrict={restrict} onChanged={() => void refresh()} />
      <button type="button" onClick={() => void onLogout()} className="mt-4 w-full text-center text-sm text-muted">
        Abmelden
      </button>
    </AuthScreen>
  );
}
