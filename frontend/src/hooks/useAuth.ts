"use client";

import { useState, useEffect, useCallback, createContext, useContext } from "react";
import { login as apiLogin } from "@/lib/api";
import type { AuthState } from "@/lib/types";

const AUTH_STORAGE_KEY = "auth-user";

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

export function useAuthState() {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    userId: null,
    isLoading: true,
  });

  // Load auth state from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(AUTH_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        setAuthState({
          isAuthenticated: true,
          userId: parsed.userId,
          isLoading: false,
        });
      } else {
        setAuthState((prev) => ({ ...prev, isLoading: false }));
      }
    } catch (err) {
      console.error("Failed to load auth state:", err);
      setAuthState((prev) => ({ ...prev, isLoading: false }));
    }
  }, []);

  const login = useCallback(async (username: string, password: string): Promise<boolean> => {
    try {
      const response = await apiLogin({ username, password });
      if (response.success && response.user_id) {
        const authData = { userId: response.user_id };
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(authData));
        setAuthState({
          isAuthenticated: true,
          userId: response.user_id,
          isLoading: false,
        });
        return true;
      }
      return false;
    } catch (err) {
      console.error("Login failed:", err);
      return false;
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    setAuthState({
      isAuthenticated: false,
      userId: null,
      isLoading: false,
    });
  }, []);

  return {
    ...authState,
    login,
    logout,
  };
}

export { AuthContext };
export type { AuthContextType };
