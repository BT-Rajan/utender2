import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { apiFetch } from "@/api/client";

export type UserRole = "owner" | "service_provider" | "admin";

export interface CurrentUser {
  id: string;
  email: string;
  role: UserRole;
  full_name: string | null;
  phone: string | null;
  language: "en" | "ar";
  email_verified: boolean;
  created_at: string;
}

interface SignupPayload {
  email: string;
  password: string;
  full_name: string;
  role: "owner" | "service_provider";
}

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (payload: SignupPayload) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const me = await apiFetch<CurrentUser>("/auth/me");
      setUser(me);
    } catch {
      setUser(null);
    }
  };

  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const me = await apiFetch<CurrentUser>("/auth/login", { method: "POST", body: { email, password } });
    setUser(me);
  };

  const signup = async (payload: SignupPayload) => {
    const me = await apiFetch<CurrentUser>("/auth/signup", { method: "POST", body: payload });
    setUser(me);
    return me;
  };

  const logout = async () => {
    await apiFetch("/auth/logout", { method: "POST" });
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, refresh }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
