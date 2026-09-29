"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useQuery } from "@tanstack/react-query"
import { Loader2, LogOut, ShieldCheck } from "lucide-react"
import { useSearchParams } from "next/navigation"
import { Suspense, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { Field, PageHeader, PageLoading, SectionCard, StatusBadge } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { api } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDateTime, humanize } from "@/lib/format"
import { useI18n } from "@/lib/i18n"

const pwSchema = z.object({
  current_password: z.string().min(1, "Enter your current password"),
  new_password: z.string().min(8, "Use at least 8 characters").refine((v) => /[A-Za-z]/.test(v) && /\d/.test(v), "Include letters and numbers"),
  confirm: z.string(),
}).refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Passwords do not match" })

function ChangePassword({ forced }: { forced: boolean }) {
  const { logout } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const { register, handleSubmit, reset, formState: { errors } } = useForm<z.infer<typeof pwSchema>>({ resolver: zodResolver(pwSchema) })
  const change = useApiMutation((v: z.infer<typeof pwSchema>) => api.post("/auth/change-password", { current_password: v.current_password, new_password: v.new_password }), { success: "Password changed — please sign in again", onSuccess: () => { reset(); setTimeout(() => void logout(), 800) }, silentError: true })
  return (
    <SectionCard title="Change password" description={forced ? "You must choose a new password before continuing." : "You will be signed out of every device afterwards."}>
      <form onSubmit={handleSubmit(async (v) => { setError(null); try { await change.mutateAsync(v) } catch (e) { setError((e as Error).message) } })} className="max-w-sm space-y-4" noValidate>
        {error && <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
        <Field label="Current password" error={errors.current_password?.message}>{(p) => <Input {...p} type="password" autoComplete="current-password" {...register("current_password")} />}</Field>
        <Field label="New password" error={errors.new_password?.message} hint="8+ characters, letters and numbers">{(p) => <Input {...p} type="password" autoComplete="new-password" {...register("new_password")} />}</Field>
        <Field label="Confirm new password" error={errors.confirm?.message}>{(p) => <Input {...p} type="password" autoComplete="new-password" {...register("confirm")} />}</Field>
        <Button type="submit" disabled={change.isPending}>{change.isPending && <Loader2 className="size-4 animate-spin" />}Update password</Button>
      </form>
    </SectionCard>
  )
}

function TwoFactor() {
  const { user, refreshUser } = useAuth()
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null)
  const [code, setCode] = useState("")
  const [error, setError] = useState<string | null>(null)
  const start = useApiMutation(() => api.post<{ secret: string; otpauth_uri: string }>("/auth/2fa/setup"), { onSuccess: setSetup })
  const enable = useApiMutation(() => api.post("/auth/2fa/enable", { code }), { success: "Two-factor authentication enabled", onSuccess: () => { setSetup(null); setCode(""); void refreshUser() }, silentError: true })
  const disable = useApiMutation(() => api.post("/auth/2fa/disable", { code }), { success: "Two-factor authentication disabled", onSuccess: () => { setCode(""); void refreshUser() }, silentError: true })
  return (
    <SectionCard title="Two-factor authentication" description="Add a one-time code from an authenticator app (Google Authenticator, Microsoft Authenticator, Authy) to sign-in.">
      {user?.totp_enabled ? (
        <div className="space-y-3">
          <p className="flex items-center gap-2 text-sm"><ShieldCheck className="size-4 text-success" /> Enabled on your account.</p>
          <div className="flex max-w-xs gap-2"><Input inputMode="numeric" maxLength={8} placeholder="6-digit code" aria-label="Authenticator code" value={code} onChange={(e) => setCode(e.target.value)} /><Button variant="outline" disabled={code.length < 6 || disable.isPending} onClick={async () => { setError(null); try { await disable.mutateAsync() } catch (e) { setError((e as Error).message) } }}>Disable</Button></div>
        </div>
      ) : setup ? (
        <div className="space-y-3">
          <p className="text-sm">Add this key in your authenticator app, then enter the 6-digit code it shows:</p>
          <code className="block w-fit rounded-lg bg-muted px-3 py-2 font-mono text-sm tracking-widest break-all select-all">{setup.secret}</code>
          <p className="text-xs text-muted-foreground">Or open <a className="text-primary underline" href={setup.otpauth_uri}>the setup link</a> on a phone with an authenticator installed.</p>
          <div className="flex max-w-xs gap-2"><Input inputMode="numeric" maxLength={8} placeholder="123456" aria-label="Authenticator code" value={code} onChange={(e) => setCode(e.target.value)} autoFocus /><Button disabled={code.length < 6 || enable.isPending} onClick={async () => { setError(null); try { await enable.mutateAsync() } catch (e) { setError((e as Error).message) } }}>Verify & enable</Button></div>
        </div>
      ) : (
        <Button variant="outline" onClick={() => start.mutate()} disabled={start.isPending}>Set up two-factor authentication</Button>
      )}
      {error && <p className="mt-2 text-sm text-destructive" role="alert">{error}</p>}
    </SectionCard>
  )
}

interface Session { id: number; created_at: string; ip_address: string | null; user_agent: string | null; current: boolean }

function Sessions() {
  const list = useQuery({ queryKey: ["sessions"], queryFn: () => api.get<Session[]>("/auth/sessions") })
  const revoke = useApiMutation((id: number) => api.delete(`/auth/sessions/${id}`), { success: "Session signed out", invalidate: [["sessions"]] })
  return (
    <SectionCard title="Active sessions" description="Devices currently signed in to your account.">
      <ul className="divide-y rounded-lg border">
        {list.data?.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-sm">
            <div className="min-w-0"><p className="truncate">{s.user_agent ?? "Unknown device"} {s.current && <StatusBadge status="ACTIVE" tone="info" label="This device" />}</p><p className="text-xs text-muted-foreground">{s.ip_address ?? "—"} · {formatDateTime(s.created_at)}</p></div>
            {!s.current && <Button variant="ghost" size="sm" onClick={() => revoke.mutate(s.id)}><LogOut className="size-4" /> Sign out</Button>}
          </li>
        ))}
        {list.isLoading && <li className="px-4 py-4"><Loader2 className="size-4 animate-spin text-muted-foreground" /></li>}
      </ul>
    </SectionCard>
  )
}

function ProfileInner() {
  const { user } = useAuth()
  const { locale, setLocale } = useI18n()
  const forced = useSearchParams().get("change-password") === "1" || !!user?.must_change_password
  if (!user) return <PageLoading />
  return (
    <>
      <PageHeader title="My profile" description={`${user.full_name} · ${user.email}`} />
      <div className="grid max-w-3xl gap-4">
        <SectionCard title="Account">
          <dl className="grid gap-x-8 text-sm sm:grid-cols-2">
            <div className="py-1.5"><dt className="text-muted-foreground">Role</dt><dd className="font-medium">{user.role_names.map((r) => humanize(r.toLowerCase())).join(", ")}</dd></div>
            <div className="py-1.5"><dt className="text-muted-foreground">Last sign-in</dt><dd className="font-medium">{user.last_login_at ? formatDateTime(user.last_login_at) : "—"}</dd></div>
            <div className="py-1.5"><dt className="text-muted-foreground">Discount limit</dt><dd className="font-medium">{user.max_discount_percent !== null ? `${user.max_discount_percent}%` : "Shop default"}</dd></div>
            <div className="py-1.5"><dt className="text-muted-foreground">Language</dt><dd><select aria-label="Language" value={locale} onChange={(e) => { setLocale(e.target.value as "en" | "bn"); void api.patch("/auth/me", { language: e.target.value }) }} className="h-8 rounded-md border bg-background px-2 text-sm"><option value="en">English</option><option value="bn">বাংলা</option></select></dd></div>
          </dl>
        </SectionCard>
        <ChangePassword forced={forced} />
        <TwoFactor />
        <Sessions />
      </div>
    </>
  )
}

export function ProfilePage() {
  return <Suspense fallback={<PageLoading />}><ProfileInner /></Suspense>
}
