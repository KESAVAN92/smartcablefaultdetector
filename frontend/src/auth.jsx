import React, { createContext, useState, useEffect } from "react";

export const AuthContext = createContext({ token: null, role: null, login: async () => {}, logout: () => {} });

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem("cfd_token") || null);
  const [role, setRole] = useState(() => localStorage.getItem("cfd_role") || null);

  useEffect(() => {
    if (token) localStorage.setItem("cfd_token", token); else localStorage.removeItem("cfd_token");
    if (role) localStorage.setItem("cfd_role", role); else localStorage.removeItem("cfd_role");
  }, [token, role]);

  async function login(email, password) {
    const res = await fetch("/api/module4/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error("Login failed");
    const j = await res.json();
    setToken(j.access_token);
    setRole(j.role);
    return j;
  }

  function logout() {
    setToken(null);
    setRole(null);
  }

  return (
    <AuthContext.Provider value={{ token, role, login, logout }}>{children}</AuthContext.Provider>
  );
}

export default AuthProvider;
