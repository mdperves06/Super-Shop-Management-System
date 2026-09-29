"use client"

import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query"
import { toast } from "sonner"

import { errorMessage } from "@/lib/api"

interface Options<TData, TVars> {
  success?: string | ((data: TData, vars: TVars) => string)
  invalidate?: QueryKey[]
  onSuccess?: (data: TData, vars: TVars) => void
  silentError?: boolean
}

/** useMutation with toast feedback and cache invalidation. Errors are shown to the user, never swallowed. */
export function useApiMutation<TData = unknown, TVars = void>(fn: (vars: TVars) => Promise<TData>, options: Options<TData, TVars> = {}) {
  const qc = useQueryClient()
  return useMutation<TData, Error, TVars>({
    mutationFn: fn,
    onSuccess: (data, vars) => {
      if (options.success) toast.success(typeof options.success === "function" ? options.success(data, vars) : options.success)
      for (const key of options.invalidate ?? []) void qc.invalidateQueries({ queryKey: key })
      options.onSuccess?.(data, vars)
    },
    onError: (err) => {
      if (!options.silentError) toast.error(errorMessage(err))
    },
  })
}
