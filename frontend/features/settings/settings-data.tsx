"use client"

import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, Database, Download, FileUp, History, Loader2, XCircle } from "lucide-react"
import { useRef, useState } from "react"

import { ConfirmDialog } from "@/components/shared/dialogs"
import { NativeSelect, SectionCard } from "@/components/shared/ui-parts"
import { Button } from "@/components/ui/button"
import { useApiMutation } from "@/hooks/use-api-mutation"
import { useRouter } from "next/navigation"

import { api, downloadFile, tokenStore } from "@/lib/api"
import { useAuth } from "@/lib/auth"
import { formatDateTime } from "@/lib/format"
import type { BackupFile, ImportResult } from "@/types/api"

const KINDS = [
  { value: "products", label: "Products", perm: "product.import", hint: "Columns: sku, name, unit, selling_price are required. Optional opening_stock creates an adjustment with a reason." },
  { value: "customers", label: "Customers", perm: "customer.import", hint: "Phone numbers must be unique. opening_balance is recorded in the customer ledger." },
  { value: "suppliers", label: "Suppliers", perm: "import.manage", hint: "opening_balance is recorded as an amount you owe." },
]
const EXPORTS = [["products", "Products"], ["inventory", "Inventory"], ["sales", "Sales"], ["purchases", "Purchases"], ["customers", "Customers"], ["suppliers", "Suppliers"]] as const

export function ImportExportSettings() {
  const { can } = useAuth()
  const allowed = KINDS.filter((k) => can(k.perm) || can("import.manage"))
  const [kind, setKind] = useState(allowed[0]?.value ?? "products")
  const [file, setFile] = useState<File | null>(null)
  const [skip, setSkip] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const current = KINDS.find((k) => k.value === kind)
  const run = useApiMutation(
    (dry: boolean) => { const f = new FormData(); f.append("file", file!); f.append("dry_run", String(dry)); f.append("skip_invalid", String(skip)); return api.upload<ImportResult>(`/admin/import/${kind}`, f) },
    { onSuccess: (r) => setResult(r), invalidate: [["products"], ["customers"], ["suppliers"], ["stock"]] },
  )
  return (
    <div className="space-y-4">
      {allowed.length > 0 && (
        <SectionCard title="Import from CSV" description="Everything is validated first. Nothing is saved until you confirm.">
          <div className="grid gap-4 md:grid-cols-[220px_1fr]">
            <div className="space-y-2">
              <label className="text-[13px] font-medium" htmlFor="import-kind">What are you importing?</label>
              <NativeSelect id="import-kind" value={kind} onChange={(e) => { setKind(e.target.value); setResult(null) }}>{allowed.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}</NativeSelect>
              <Button variant="outline" className="w-full" onClick={() => void downloadFile(`/admin/import/${kind}/template`, `${kind}-template.csv`)}><Download className="size-4" /> Download template</Button>
            </div>
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">{current?.hint}</p>
              <div className="flex flex-wrap items-center gap-2">
                <input ref={fileRef} type="file" accept=".csv,text/csv" className="sr-only" aria-label="CSV file" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null) }} />
                <Button variant="outline" onClick={() => fileRef.current?.click()}><FileUp className="size-4" /> {file ? file.name : "Choose CSV file"}</Button>
                <Button disabled={!file || run.isPending} onClick={() => run.mutate(true)}>{run.isPending && <Loader2 className="size-4 animate-spin" />}Validate</Button>
              </div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-primary" checked={skip} onChange={(e) => setSkip(e.target.checked)} /> If some rows are invalid, import only the valid ones</label>
              {result && (
                <div className="rounded-xl border p-4" role="status">
                  <p className="flex items-center gap-2 font-medium">
                    {result.error_count === 0 ? <CheckCircle2 className="size-5 text-success" /> : <XCircle className="size-5 text-destructive" />}
                    {result.committed ? `Imported ${result.imported} row(s)` : result.error_count === 0 ? `All ${result.total_rows} rows are valid` : `${result.error_count} problem(s) found in ${result.total_rows} rows`}
                  </p>
                  {result.errors.length > 0 && (
                    <ul className="scroll-thin mt-3 max-h-56 divide-y overflow-y-auto rounded-lg border text-sm">{result.errors.map((e, i) => <li key={i} className="flex gap-3 px-3 py-1.5"><span className="w-16 shrink-0 font-mono text-xs text-muted-foreground">Row {e.row}</span><span className="text-destructive">{e.message}</span></li>)}</ul>
                  )}
                  {result.dry_run && result.valid_rows > 0 && !result.committed && (
                    <Button className="mt-3" onClick={() => run.mutate(false)} disabled={run.isPending || (result.error_count > 0 && !skip)}>Import {skip ? result.valid_rows : result.total_rows} row(s)</Button>
                  )}
                </div>
              )}
            </div>
          </div>
        </SectionCard>
      )}
      <SectionCard title="Export data" description="Download CSV or Excel copies for accounting or backup.">
        <div className="flex flex-wrap gap-2">
          {EXPORTS.map(([k, label]) => (
            <div key={k} className="flex overflow-hidden rounded-lg border">
              <span className="bg-muted px-3 py-2 text-sm font-medium">{label}</span>
              <button className="border-l px-3 text-sm hover:bg-muted" onClick={() => void downloadFile(`/exports/${k}`, `${k}.csv`, { format: "csv" })}>CSV</button>
              <button className="border-l px-3 text-sm hover:bg-muted" onClick={() => void downloadFile(`/exports/${k}`, `${k}.xlsx`, { format: "xlsx" })}>Excel</button>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  )
}

export function BackupSettings() {
  const router = useRouter()
  const [restoring, setRestoring] = useState<BackupFile | null>(null)
  const list = useQuery({ queryKey: ["backups"], queryFn: () => api.get<BackupFile[]>("/admin/backups") })
  const create = useApiMutation(() => api.post<{ name: string }>("/admin/backups"), { success: (b) => `Backup ${b.name} created`, invalidate: [["backups"]] })
  const restore = useApiMutation((name: string) => api.post(`/admin/backups/${name}/restore`, { confirm: name }), { success: "Database restored — please sign in again" })
  return (
    <div className="space-y-4">
      <SectionCard title="Database backups" description="A backup is a full snapshot of every record. Keep copies off this computer."
        actions={<Button onClick={() => create.mutate()} disabled={create.isPending}>{create.isPending ? <Loader2 className="size-4 animate-spin" /> : <Database className="size-4" />} Back up now</Button>}>
        {list.isLoading ? <Loader2 className="mx-auto my-6 size-5 animate-spin text-muted-foreground" /> : (list.data?.length ?? 0) === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No backups yet. Create the first one now.</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {list.data!.map((b) => (
              <li key={b.name} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
                <div><p className="font-mono text-sm">{b.name}</p><p className="text-xs text-muted-foreground">{formatDateTime(b.created_at)} · {(b.size / 1024 / 1024).toFixed(2)} MB</p></div>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => void downloadFile(`/admin/backups/${b.name}/download`, b.name)}><Download className="size-4" /> Download</Button>
                  <Button variant="outline" size="sm" onClick={() => setRestoring(b)}><History className="size-4" /> Restore</Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
      <SectionCard title="Production (PostgreSQL)">
        <p className="text-sm text-muted-foreground">On PostgreSQL the same buttons run <code className="rounded bg-muted px-1">pg_dump</code>/<code className="rounded bg-muted px-1">pg_restore</code> when they are installed on the server. Schedule nightly dumps with your host’s tooling — see docs/DEPLOYMENT.md.</p>
      </SectionCard>
      <ConfirmDialog open={!!restoring} onOpenChange={(o) => !o && setRestoring(null)} destructive title="Restore this backup?" confirmLabel="Restore database"
        description={<>This <strong>replaces all current data</strong> with the contents of <span className="font-mono">{restoring?.name}</span>. A safety copy of the current data is made first. Everyone will need to sign in again.</>}
        onConfirm={async () => { await restore.mutateAsync(restoring!.name); tokenStore.clear(); router.replace("/login") }} />
    </div>
  )
}
