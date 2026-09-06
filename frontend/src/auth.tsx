import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { AUTH_EVENT, api, ApiError, type User } from "./api";
import { useVisiblePoll } from "./live";

import { PRODUCT_NAME } from "./brand";

const SESSION_MSG = "Sitzung abgelaufen. Bitte erneut anmelden.";
const DEFAULT_ORG = PRODUCT_NAME;

type Ctx = {
  user: User | null;
  orgName: string;
  loading: boolean;
  refresh: () => Promise<void>;
  setUser: (u: User | null) => void;
};

const AuthContext = createContext<Ctx>({
  user: null,
  orgName: DEFAULT_ORG,
  loading: true,
  refresh: async () => {},
  setUser: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [orgName, setOrgName] = useState(DEFAULT_ORG);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async (initial = false) => {
    try {
      setUser(await api.me());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setUser(null);
      else if (initial) setUser(null);
    }
  }, []);

  useEffect(() => {
    void api
      .meta()
      .then((m) => {
        const name = m.org_name?.trim() || DEFAULT_ORG;
        setOrgName(name);
        document.title = name;
      })
      .catch(() => {});
    refresh(true).finally(() => setLoading(false));
  }, [refresh]);

  const poll = useCallback(() => {
    if (!loading) void refresh(false);
  }, [loading, refresh]);
  useVisiblePoll(15000, poll);

  useEffect(() => {
    const onUnauthorized = () => {
      sessionStorage.setItem("ze-auth-reason", SESSION_MSG);
      setUser(null);
    };
    window.addEventListener(AUTH_EVENT, onUnauthorized);
    return () => window.removeEventListener(AUTH_EVENT, onUnauthorized);
  }, []);

  return (
    <AuthContext.Provider value={{ user, orgName, loading, refresh: () => refresh(false), setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
