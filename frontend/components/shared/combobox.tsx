"use client"

import { useQuery } from "@tanstack/react-query"
import { Check, ChevronsUpDown, Loader2, X } from "lucide-react"
import { useState, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useDebounce } from "@/hooks/use-debounce"
import { cn } from "@/lib/utils"

export interface Option {
  id: number
  label: string
  hint?: string
}

/** Server-searched picker (products, customers, suppliers…). Never loads a whole table. */
export function AsyncCombobox({ value, onChange, fetcher, queryKey, placeholder = "Select…", clearable = true, disabled, id, invalid, renderOption }: {
  value: Option | null
  onChange: (option: Option | null) => void
  fetcher: (q: string) => Promise<Option[]>
  queryKey: string
  placeholder?: string
  clearable?: boolean
  disabled?: boolean
  id?: string
  invalid?: boolean
  renderOption?: (o: Option) => ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const debounced = useDebounce(q.trim(), 250)
  const { data = [], isFetching } = useQuery({
    queryKey: ["combobox", queryKey, debounced],
    queryFn: () => fetcher(debounced),
    enabled: open,
    staleTime: 10_000,
  })

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) setQ("") }}>
      <PopoverTrigger
        render={
          <Button
            id={id}
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            aria-invalid={invalid}
            disabled={disabled}
            className="w-full justify-between font-normal"
          />
        }
      >
        <span className={cn("truncate", !value && "text-muted-foreground")}>{value ? value.label : placeholder}</span>
        <span className="flex items-center gap-1">
          {clearable && value && !disabled && (
            <span
              role="button"
              tabIndex={0}
              aria-label="Clear selection"
              className="rounded p-0.5 hover:bg-muted"
              onClick={(e) => { e.stopPropagation(); onChange(null) }}
              onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); onChange(null) } }}
            >
              <X className="size-3.5" />
            </span>
          )}
          <ChevronsUpDown className="size-4 opacity-50" />
        </span>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-(--anchor-width) min-w-64 gap-0 p-0">
        <div className="border-b p-2">
          <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type to search…" aria-label="Search options" />
        </div>
        <ul className="max-h-64 overflow-y-auto p-1" role="listbox">
          {isFetching && data.length === 0 && (
            <li className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Searching…</li>
          )}
          {!isFetching && data.length === 0 && <li className="px-3 py-3 text-sm text-muted-foreground">No results</li>}
          {data.map((o) => (
            <li key={o.id} role="option" aria-selected={value?.id === o.id}>
              <button
                type="button"
                onClick={() => { onChange(o); setOpen(false) }}
                className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-accent focus-visible:bg-accent focus-visible:outline-none"
              >
                <Check className={cn("size-4 shrink-0", value?.id === o.id ? "opacity-100" : "opacity-0")} />
                {renderOption ? renderOption(o) : (
                  <span className="min-w-0"><span className="block truncate">{o.label}</span>{o.hint && <span className="block truncate text-xs text-muted-foreground">{o.hint}</span>}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  )
}
