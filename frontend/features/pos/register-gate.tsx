"use client"

import { useQuery } from "@tanstack/react-query"
import { Landmark, Loader2 } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { Field, NativeSelect } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import type { CashSession, Register } from "@/types/api"

export function useCurrentSession() {
  const { canAny } = useAuth()
  return useQuery({ queryKey: ["cash-session", "current"], queryFn: () => api.get<CashSession | null>("/cash-sessions/current"), enabled: canAny("register.use", "register.manage"), staleTime: 10_000 })
}

/** Shown instead of the POS until the cashier has an open register session (cash accountability). */
export function OpenRegisterCard({ onOpened }: { onOpened?: () => void }) {
  const { can } = useAuth()
  const registers = useQuery({ queryKey: ["registers"], queryFn: () => api.get<Register[]>("/registers") })
  const [registerId, setRegisterId] = useState("")
  const [cash, setCash] = useState("")
  const [error, setError] = useState<string | null>(null)
  const open = useApiMutation(
    () => api.post<CashSession>("/cash-sessions/open", { register_id: Number(registerId || registers.data?.[0]?.id), opening_cash: Number(cash) }),
    { success: "Register opened — happy selling!", invalidate: [["cash-session"]], onSuccess: () => onOpened?.(), silentError: true },
  )
  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (cash === "" || Number(cash) < 0) return setError("Enter the opening cash in the drawer (0 if empty).")
    try { await open.mutateAsync() } catch (err) { setError((err as Error).message) }
  }
  if (!can("register.use")) {
    return <div className="mx-auto mt-16 max-w-md text-center text-sm text-muted-foreground" role="alert">You need an open cash register to sell, and your role cannot open one. Ask a manager.</div>
  }
  return (
    <div className="mx-auto mt-10 max-w-md">
      <Card>
        <CardContent className="space-y-5 p-6">
          <div className="flex items-center gap-3">
            <span className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary"><Landmark className="size-5" /></span>
            <div><h1 className="text-lg font-semibold">Open cash register</h1><p className="text-sm text-muted-foreground">Count the drawer and enter the opening cash to start selling.</p></div>
          </div>
          <form onSubmit={submit} className="space-y-4" noValidate>
            {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
            <Field label="Register">{(p) => <NativeSelect {...p} value={registerId || String(registers.data?.[0]?.id ?? "")} onChange={(e) => setRegisterId(e.target.value)}>{registers.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</NativeSelect>}</Field>
            <Field label="Opening cash (৳)" required>{(p) => <Input {...p} type="number" min="0" step="0.01" inputMode="decimal" autoFocus value={cash} onChange={(e) => setCash(e.target.value)} className="h-12 text-lg" />}</Field>
            <Button type="submit" size="lg" className="w-full" disabled={open.isPending}>{open.isPending && <Loader2 className="size-4 animate-spin" />}Open register</Button>
          </form>
          <p className="text-center text-xs text-muted-foreground">Already open elsewhere? See <Link href="/cash-register" className="text-primary underline">Cash register</Link>.</p>
        </CardContent>
      </Card>
    </div>
  )
}
