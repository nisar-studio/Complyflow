import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../api/client';

const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Load current user from /api/auth/me using ambient HttpOnly cookie
  const loadUser = useCallback(async () => {
    try {
      const u = await api.getMe();
      setUser(u);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  const login = useCallback(async (email, password) => {
    const data = await api.login(email, password);
    setUser(data.user);
    return data;
  }, []);

  const register = useCallback(async (email, name, password) => {
    const data = await api.register(email, name, password);
    return data;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // best-effort
    }
    setUser(null);
  }, []);

  const value = { user, loading, login, register, logout };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export default AuthContext;
