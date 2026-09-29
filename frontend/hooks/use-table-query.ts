"use client"

import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"

import { useDebounce } from "@/hooks/use-debounce"
import { api } from "@/lib/api"
import type { Page } from "@/types/api"

export type Filters = Record<string, string | number | boolean | null | undefined>

interface Options {
  pageSize?: number
  filters?: Filters
  enabled?: boolean
  defaultSort?: string
}

/** Server-side pagination + debounced search + sort for any list endpoint returning Page<T>. */
export function useTableQuery<T>(queryKey: string, path: string, options: Options = {}) {
  const { pageSize = 20, filters, enabled = true, defaultSort } = options
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const [sort, setSort] = useState<string | undefined>(defaultSort)
  const debounced = useDebounce(search, 300)
  const filterKey = JSON.stringify(filters ?? {})

  useEffect(() => { setPage(1) }, [debounced, filterKey, sort]) // eslint-disable-line react-hooks/set-state-in-effect

  const params = useMemo(
    () => ({ ...(filters ?? {}), page, page_size: pageSize, search: debounced || undefined, sort }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filterKey, page, pageSize, debounced, sort],
  )

  const query = useQuery({
    queryKey: [queryKey, params],
    queryFn: () => api.get<Page<T>>(path, params as Record<string, string | number | boolean | undefined>),
    placeholderData: keepPreviousData,
    enabled,
  })

  const toggleSort = (key: string) => setSort((s) => (s === key ? `-${key}` : key))

  return { query, data: query.data, page, setPage, search, setSearch, sort, setSort, toggleSort, pageSize }
}
