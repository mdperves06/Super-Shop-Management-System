"use client"

import { useQuery } from "@tanstack/react-query"
import { createContext, useContext, useEffect, useMemo } from "react"

import { api } from "@/lib/api"
import { setFormatConfig } from "@/lib/format"
import type { Settings } from "@/types/api"

const SettingsContext = createContext<Settings>({})

/** Public shop settings (branding, locale, receipt options). Loaded once, also before login. */
export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const { data } = useQuery({ queryKey: ["settings", "public"], queryFn: () => api.get<Settings>("/settings/public"), staleTime: 5 * 60_000 })
  const settings = useMemo(() => data ?? {}, [data])
  useEffect(() => {
    setFormatConfig({
      currencySymbol: String(settings["locale.currency_symbol"] ?? "৳"),
      timezone: String(settings["locale.timezone"] ?? "Asia/Dhaka"),
      dateFormat: String(settings["locale.date_format"] ?? "DD/MM/YYYY"),
    })
  }, [settings])
  return <SettingsContext.Provider value={settings}>{children}</SettingsContext.Provider>
}

export function useShopSettings(): Settings {
  return useContext(SettingsContext)
}
