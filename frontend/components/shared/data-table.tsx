"use client"

import { AlertCircle, ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Inbox, RefreshCw, Search } from "lucide-react"
import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useT } from "@/lib/i18n"
import { cn } from "@/lib/utils"
import type { Page } from "@/types/api"

export interface Column<T> {
  id: string
  header: ReactNode
  cell: (row: T) => ReactNode
  align?: "left" | "right" | "center"
  className?: string
  sortKey?: string
  /** hide below the md breakpoint to keep phone tables readable */
  hideOnMobile?: boolean
}

interface DataTableProps<T> {
  columns: Column<T>[]
  page?: Page<T>
  isLoading?: boolean
  isFetching?: boolean
  error?: Error | null
  onRetry?: () => void
  onPageChange?: (page: number) => void
  sort?: string
  onSort?: (key: string) => void
  rowKey: (row: T) => string | number
  onRowClick?: (row: T) => void
  empty?: { title: string; description?: string; action?: ReactNode }
  caption?: string
}

const alignClass = { left: "text-left", right: "text-right", center: "text-center" }

export function DataTable<T>({
  columns, page, isLoading, isFetching, error, onRetry, onPageChange, sort, onSort, rowKey, onRowClick, empty, caption,
}: DataTableProps<T>) {
  const t = useT()
  const rows = page?.items ?? []

  if (error && !page) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border bg-card px-6 py-14 text-center" role="alert">
        <AlertCircle className="size-8 text-destructive" aria-hidden />
        <div>
          <p className="font-medium">We couldn’t load this data</p>
          <p className="mt-1 text-sm text-muted-foreground">{error.message}</p>
        </div>
        {onRetry && <Button variant="outline" onClick={onRetry}><RefreshCw className="size-4" /> Try again</Button>}
      </div>
    )
  }

  const showSkeleton = isLoading && !page
  if (!showSkeleton && rows.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed bg-card px-6 py-16 text-center">
        <span className="flex size-12 items-center justify-center rounded-full bg-muted"><Inbox className="size-6 text-muted-foreground" aria-hidden /></span>
        <div>
          <p className="font-medium">{empty?.title ?? t("common.noResults")}</p>
          {empty?.description && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{empty.description}</p>}
        </div>
        {empty?.action}
      </div>
    )
  }

  const from = page ? (page.page - 1) * page.page_size + 1 : 0
  const to = page ? Math.min(page.page * page.page_size, page.total) : 0

  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <div className={cn("scroll-thin overflow-x-auto transition-opacity", isFetching && !isLoading && "opacity-70")}>
        <Table>
          {caption && <caption className="sr-only">{caption}</caption>}
          <TableHeader>
            <TableRow className="bg-muted/50 hover:bg-muted/50">
              {columns.map((c) => {
                const sorted = sort === c.sortKey ? "asc" : sort === `-${c.sortKey}` ? "desc" : null
                return (
                  <TableHead
                    key={c.id}
                    scope="col"
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                    className={cn("h-10 whitespace-nowrap text-xs font-semibold tracking-wide text-muted-foreground uppercase", alignClass[c.align ?? "left"], c.hideOnMobile && "hidden md:table-cell", c.className)}
                  >
                    {c.sortKey && onSort ? (
                      <button type="button" onClick={() => onSort(c.sortKey!)} className="inline-flex items-center gap-1 uppercase hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
                        {c.header}
                        {sorted === "asc" ? <ArrowUp className="size-3" /> : sorted === "desc" ? <ArrowDown className="size-3" /> : null}
                      </button>
                    ) : c.header}
                  </TableHead>
                )
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {showSkeleton
              ? Array.from({ length: 8 }).map((_, i) => (
                  <TableRow key={i}>
                    {columns.map((c) => (
                      <TableCell key={c.id} className={cn(c.hideOnMobile && "hidden md:table-cell")}><Skeleton className="h-4 w-full max-w-40" /></TableCell>
                    ))}
                  </TableRow>
                ))
              : rows.map((row) => (
                  <TableRow
                    key={rowKey(row)}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={cn(onRowClick && "cursor-pointer")}
                  >
                    {columns.map((c) => (
                      <TableCell key={c.id} className={cn("py-2.5", alignClass[c.align ?? "left"], c.hideOnMobile && "hidden md:table-cell", c.className)}>
                        {c.cell(row)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </div>
      {page && page.total > 0 && onPageChange && (
        <div className="flex flex-col items-center justify-between gap-2 border-t px-4 py-2.5 text-sm text-muted-foreground sm:flex-row">
          <span className="tabular">{t("common.rowsOf", { from, to, total: page.total })}</span>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="sm" disabled={page.page <= 1} onClick={() => onPageChange(page.page - 1)} aria-label={t("common.previous")}>
              <ChevronLeft className="size-4" />
            </Button>
            <span className="min-w-24 text-center tabular">{t("common.page", { page: page.page, pages: page.pages })}</span>
            <Button variant="outline" size="sm" disabled={page.page >= page.pages} onClick={() => onPageChange(page.page + 1)} aria-label={t("common.next")}>
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export function SearchInput({ value, onChange, placeholder, className }: { value: string; onChange: (v: string) => void; placeholder?: string; className?: string }) {
  const t = useT()
  return (
    <div className={cn("relative w-full sm:max-w-xs", className)}>
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder ?? t("common.search")} aria-label={placeholder ?? t("common.search")} className="pl-9" />
    </div>
  )
}

export function Toolbar({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mb-4 flex flex-wrap items-center gap-2", className)}>{children}</div>
}
