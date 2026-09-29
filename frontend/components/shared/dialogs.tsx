"use client"

import { Loader2 } from "lucide-react"
import { useState, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"

export function FormDialog({ open, onOpenChange, title, description, children, size = "md", footer }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  children: ReactNode
  size?: "sm" | "md" | "lg" | "xl"
  footer?: ReactNode
}) {
  const width = { sm: "sm:max-w-sm", md: "sm:max-w-lg", lg: "sm:max-w-2xl", xl: "sm:max-w-4xl" }[size]
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn("max-h-[92vh] gap-4 overflow-y-auto", width)}>
        <DialogHeader>
          <DialogTitle className="text-base font-semibold">{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        {children}
        {footer && <DialogFooter>{footer}</DialogFooter>}
      </DialogContent>
    </Dialog>
  )
}

export function SubmitRow({ onCancel, submitting, submitLabel = "Save", disabled }: { onCancel: () => void; submitting?: boolean; submitLabel?: string; disabled?: boolean }) {
  return (
    <div className="flex justify-end gap-2 pt-2">
      <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>Cancel</Button>
      <Button type="submit" disabled={submitting || disabled}>
        {submitting && <Loader2 className="size-4 animate-spin" aria-hidden />}
        {submitLabel}
      </Button>
    </div>
  )
}

/** Confirmation for destructive / irreversible actions. Optionally collects a mandatory reason. */
export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel = "Confirm", destructive, onConfirm, reason }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: ReactNode
  confirmLabel?: string
  destructive?: boolean
  onConfirm: (reason?: string) => Promise<unknown> | void
  reason?: { label: string; minLength?: number }
}) {
  const [text, setText] = useState("")
  const [busy, setBusy] = useState(false)
  const tooShort = !!reason && text.trim().length < (reason.minLength ?? 3)

  async function run() {
    setBusy(true)
    try {
      await onConfirm(reason ? text.trim() : undefined)
      setText("")
      onOpenChange(false)
    } catch {
      /* the caller surfaces the error; keep the dialog open so nothing is lost */
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!busy) onOpenChange(o) }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        {reason && (
          <div className="space-y-1.5">
            <label htmlFor="confirm-reason" className="text-[13px] font-medium">{reason.label}</label>
            <Textarea id="confirm-reason" value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder="Required" />
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button variant={destructive ? "destructive" : "default"} onClick={run} disabled={busy || tooShort}>
            {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
