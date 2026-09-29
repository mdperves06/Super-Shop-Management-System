"use client"

import { Loader2, ShieldAlert } from "lucide-react"
import Link from "next/link"
import { forwardRef, useId, type ReactNode, type SelectHTMLAttributes } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/lib/auth"
import { formatMoney, humanize } from "@/lib/format"
import { cn } from "@/lib/utils"

export function PageHeader({ title, description, actions, back }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; back?: { href: string; label: string } }) {
  return (
    <div className="no-print mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {back && <Link href={back.href} className="mb-1 inline-block text-sm text-muted-foreground hover:text-foreground">← {back.label}</Link>}
        <h1 className="truncate text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

const TONES: Record<string, string> = {
  success: "bg-success/12 text-success border-success/25",
  warning: "bg-warning/15 text-[oklch(0.5_0.12_75)] dark:text-warning border-warning/30",
  danger: "bg-destructive/10 text-destructive border-destructive/25",
  info: "bg-info/12 text-info border-info/25",
  neutral: "bg-muted text-muted-foreground border-border",
}

const STATUS_TONE: Record<string, keyof typeof TONES> = {
  COMPLETED: "success", RECEIVED: "success", ACTIVE: "success", OPEN: "info", APPROVED: "info", PAID: "success", ok: "success", PRESENT: "success",
  PENDING: "warning", PARTIALLY_RECEIVED: "warning", PARTIAL: "warning", low: "warning", DRAFT: "neutral", CLOSED: "neutral", NONE: "neutral", INACTIVE: "neutral",
  VOIDED: "danger", VOID: "danger", CANCELLED: "danger", out: "danger", FULL: "danger", TERMINATED: "danger", EXPIRED: "danger",
  warning: "warning", critical: "danger", info: "info",
}

export function StatusBadge({ status, label, tone }: { status: string; label?: string; tone?: keyof typeof TONES }) {
  const t = tone ?? STATUS_TONE[status] ?? "neutral"
  const text = label ?? ({ ok: "In stock", low: "Low", out: "Out of stock" } as Record<string, string>)[status] ?? humanize(status.toLowerCase())
  return <Badge variant="outline" className={cn("font-medium whitespace-nowrap", TONES[t])}>{text}</Badge>
}

export function Money({ value, className, signed }: { value: number | null | undefined; className?: string; signed?: boolean }) {
  const negative = (value ?? 0) < 0
  return (
    <span className={cn("tabular whitespace-nowrap", signed && negative && "text-destructive", signed && !negative && (value ?? 0) > 0 && "text-success", className)}>
      {formatMoney(value)}
    </span>
  )
}

export function StatCard({ label, value, hint, icon, tone = "neutral", href, loading }: {
  label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; tone?: "neutral" | "danger" | "warning" | "success"; href?: string; loading?: boolean
}) {
  const body = (
    <Card className={cn("h-full transition-shadow", href && "hover:shadow-md")}>
      <CardContent className="flex items-start justify-between gap-3 p-4">
        <div className="min-w-0">
          <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
          {loading ? <Skeleton className="mt-2 h-7 w-28" /> : <p className={cn("mt-1 text-xl leading-tight font-semibold break-words tabular xl:text-2xl", tone === "danger" && "text-destructive", tone === "warning" && "text-[oklch(0.55_0.13_70)] dark:text-warning", tone === "success" && "text-success")}>{value}</p>}
          {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
        </div>
        {icon && <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">{icon}</span>}
      </CardContent>
    </Card>
  )
  return href ? <Link href={href} className="block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring">{body}</Link> : body
}

export function EmptyState({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed bg-card px-6 py-14 text-center">
      {icon && <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">{icon}</span>}
      <div>
        <p className="font-medium">{title}</p>
        {description && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  )
}

export function PageLoading() {
  return (
    <div className="flex min-h-64 items-center justify-center" role="status" aria-live="polite">
      <Loader2 className="size-6 animate-spin text-muted-foreground" aria-hidden />
      <span className="sr-only">Loading…</span>
    </div>
  )
}

export function CardSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <Card><CardContent className="space-y-3 p-4">{Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-5 w-full" />)}</CardContent></Card>
  )
}

/** Page-level permission guard. The backend still enforces every rule; this only avoids a dead-end UI. */
export function RequirePermission({ any, children }: { any: string[]; children: ReactNode }) {
  const { canAny } = useAuth()
  if (canAny(...any)) return <>{children}</>
  return (
    <div className="mx-auto mt-16 flex max-w-md flex-col items-center gap-3 text-center" role="alert">
      <span className="flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive"><ShieldAlert className="size-6" aria-hidden /></span>
      <h1 className="text-xl font-semibold">You don’t have access to this page</h1>
      <p className="text-sm text-muted-foreground">Ask an administrator to grant the required permission if you need it.</p>
      <Button variant="outline" render={<Link href="/" />}>Go to my home page</Button>
    </div>
  )
}

export function Can({ perm, children }: { perm: string | string[]; children: ReactNode }) {
  const { canAny } = useAuth()
  return canAny(...(Array.isArray(perm) ? perm : [perm])) ? <>{children}</> : null
}

/* ---------- form controls ---------- */

export const NativeSelect = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function NativeSelect({ className, children, ...props }, ref) {
  return (
    <select
      ref={ref}
      {...props}
      className={cn(
        "h-9 w-full min-w-0 rounded-lg border border-input bg-background px-2.5 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive dark:bg-input/30",
        className,
      )}
    >
      {children}
    </select>
  )
})

export function Field({ label, error, hint, required, children, className }: {
  label: string; error?: string; hint?: string; required?: boolean; children: (props: { id: string; "aria-invalid": boolean; "aria-describedby"?: string }) => ReactNode; className?: string
}) {
  const id = useId()
  const describedBy = error ? `${id}-err` : hint ? `${id}-hint` : undefined
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id} className="text-[13px] font-medium">{label}{required && <span className="text-destructive" aria-hidden> *</span>}</Label>
      {children({ id, "aria-invalid": !!error, "aria-describedby": describedBy })}
      {error ? <p id={`${id}-err`} className="text-xs text-destructive" role="alert">{error}</p> : hint ? <p id={`${id}-hint`} className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  )
}

export function SectionCard({ title, description, actions, children, className }: { title?: ReactNode; description?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <Card className={className}>
      {(title || actions) && (
        <div className="flex items-start justify-between gap-3 px-4 pt-4">
          <div>
            {title && <h2 className="text-sm font-semibold">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <CardContent className="p-4">{children}</CardContent>
    </Card>
  )
}

export function KeyValue({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium tabular">{children}</dd>
    </div>
  )
}
