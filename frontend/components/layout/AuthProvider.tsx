"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, clearToken, getToken, redirectToLogin } from "@/lib/api";
import type { User } from "@/lib/types";

interface AuthValue {
  user: User;
  logout: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

/** Guards every console page: no token or a rejected token means back to /login. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!getToken()) {
      redirectToLogin("signin");
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => {
        /* a 401 already redirected; a network error leaves the loading state */
      });
  }, []);

  if (!user) return <p className="p-8 text-sm text-slate-500">Loading...</p>;

  const logout = () => {
    clearToken();
    redirectToLogin("signed_out");
  };
  return <AuthContext.Provider value={{ user, logout }}>{children}</AuthContext.Provider>;
}
