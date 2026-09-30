"use client"

import { useQueryClient } from "@tanstack/react-query"
import { useRouter } from "next/navigation"
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"

import { ApiError, api, restoreSession, tokenStore } from "@/lib/api"
import type { Me } from "@/types/api"

type Status = "loading" | "authenticated" | "anonymous"

interface AuthValue {
  user: Me | null
  status: Status
  login: (email: string, password: string, otp?: string) => Promise<Me>
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  can: (permission: string) => boolean
  canAny: (...permissions: string[]) => boolean
}

const AuthContext = createContext<AuthValue | null>(null)

interface LoginResponse {
  access_token: string
  user: Me
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [status, setStatus] = useState<Status>("loading")
  const router = useRouter()
  const qc = useQueryClient()

  const loadUser = useCallback(async () => {
    if (!(await restoreSession())) {
      setUser(null)
      setStatus("anonymous")
      return
    }
    try {
      const me = await api.get<Me>("/auth/me")
      setUser(me)
      setStatus("authenticated")
    } catch (e) {
      if (e instanceof ApiError && e.status === 0) {
        setStatus("loading") // backend unreachable: stay on the splash instead of bouncing to login
        return
      }
      tokenStore.clear()
      setUser(null)
      setStatus("anonymous")
    }
  }, [])

  useEffect(() => {
    void loadUser() // eslint-disable-line react-hooks/set-state-in-effect
  }, [loadUser])

  useEffect(() => {
    const onLogout = () => {
      setUser(null)
      setStatus("anonymous")
      qc.clear()
      router.replace("/login")
    }
    window.addEventListener("ssm:logout", onLogout)
    return () => window.removeEventListener("ssm:logout", onLogout)
  }, [qc, router])

  const login = useCallback(async (email: string, password: string, otp?: string) => {
    const res = await api.post<LoginResponse>("/auth/login", { email, password, otp: otp || undefined })
    tokenStore.set(res.access_token)
    setUser(res.user)
    setStatus("authenticated")
    return res.user
  }, [])

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout") } catch { /* already expired */ }
    tokenStore.clear()
    setUser(null)
    setStatus("anonymous")
    qc.clear()
    router.replace("/login")
  }, [qc, router])

  const value = useMemo<AuthValue>(() => {
    const perms = new Set(user?.permissions ?? [])
    return {
      user,
      status,
      login,
      logout,
      refreshUser: loadUser,
      can: (p) => perms.has(p),
      canAny: (...ps) => ps.some((p) => perms.has(p)),
    }
  }, [user, status, login, logout, loadUser])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>")
  return ctx
}
