"use client"

import { useQuery } from "@tanstack/react-query"
import { Hourglass, ShieldCheck, ShieldX } from "lucide-react"
import { useMemo, useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { api } from "@/lib/api"
import type { DiscountRequest } from "@/types/api"

interface Requested { id: number; cartKey: string }

/**
 * Tracks the manager approval for the current basket. An approval is bound to the exact cart, so it is only
 * honoured while the cart is unchanged; editing the cart invalidates it and a new request is needed.
 */
export function useDiscountApproval(payload: object, needed: boolean) {
  const cartKey = useMemo(() => JSON.stringify(payload), [payload])
  const [requested, setRequested] = useState<Requested | null>(null)
  const current = requested && requested.cartKey === cartKey ? requested : null

  const status = useQuery({
    queryKey: ["discount-request", current?.id],
    queryFn: () => api.get<DiscountRequest>(`/discount-requests/${current!.id}`),
    enabled: needed && !!current,
    refetchInterval: (q) => (q.state.data?.status === "PENDING" ? 4000 : false),
  })
  const request = useMutationRequest(payload, cartKey, setRequested)
  const state = needed && current ? status.data : undefined
  return {
    request: state,
    approvedId: needed && state?.status === "APPROVED" ? state.id : undefined,
    submit: request.mutate,
    submitting: request.isPending,
  }
}

function useMutationRequest(payload: object, cartKey: string, set: (r: Requested) => void) {
  return useApiMutation(
    (reason: string) => api.post<DiscountRequest>("/discount-requests", { ...payload, reason }),
    { success: "Sent to a manager for approval", onSuccess: (r) => set({ id: r.id, cartKey }) },
  )
}

export function DiscountApprovalPanel({ approval, percent, limit }: {
  approval: ReturnType<typeof useDiscountApproval>
  percent: number
  limit: number
}) {
  const [reason, setReason] = useState("")
  const r = approval.request
  if (r?.status === "PENDING") {
    return <p className="flex items-center gap-1.5 rounded-md bg-warning/15 px-2 py-1.5 text-xs" role="status"><Hourglass className="size-3.5" />Waiting for a manager to approve {r.discount_percent}%…</p>
  }
  if (r?.status === "APPROVED") {
    return <p className="flex items-center gap-1.5 rounded-md bg-success/12 px-2 py-1.5 text-xs text-success" role="status"><ShieldCheck className="size-3.5" />Approved by {r.decided_by_name}. You can take payment.</p>
  }
  return (
    <div className="space-y-1.5 rounded-md bg-warning/15 px-2 py-1.5 text-xs" role="alert">
      {r?.status === "REJECTED" && <p className="flex items-center gap-1.5 text-destructive"><ShieldX className="size-3.5" />Rejected{r.decision_note ? `: ${r.decision_note}` : ""}. Lower the discount or ask again.</p>}
      {r?.status === "EXPIRED" && <p className="text-destructive">The last approval expired. Ask again.</p>}
      <p>Discount {percent}% is above your {limit}% limit. Ask a manager to approve it:</p>
      <div className="flex gap-1.5">
        <Input aria-label="Reason for discount" placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} className="h-8 text-xs" maxLength={500} />
        <Button size="sm" disabled={reason.trim().length < 3 || approval.submitting} onClick={() => approval.submit(reason.trim())}>Request</Button>
      </div>
    </div>
  )
}
