"use client"

import { useEffect, useState, type ReactNode } from "react"
import { createPortal } from "react-dom"

/**
 * Renders children into #print-root (a sibling of the app in <body>). While printing, CSS hides the app
 * and shows only #print-root, so receipts / invoices / reports print cleanly without the surrounding UI.
 */
export function PrintPortal({ children }: { children: ReactNode }) {
  const [root, setRoot] = useState<HTMLElement | null>(null)
  useEffect(() => {
    let el = document.getElementById("print-root")
    if (!el) {
      el = document.createElement("div")
      el.id = "print-root"
      document.body.appendChild(el)
    }
    setRoot(el) // eslint-disable-line react-hooks/set-state-in-effect
  }, [])
  return root ? createPortal(children, root) : null
}

/** Print with an optional custom @page size (e.g. 80mm thermal roll). */
export function printPage(pageCss?: string) {
  let style: HTMLStyleElement | null = null
  if (pageCss) {
    style = document.createElement("style")
    style.textContent = `@media print { @page { ${pageCss} } }`
    document.head.appendChild(style)
  }
  const cleanup = () => {
    style?.remove()
    window.removeEventListener("afterprint", cleanup)
  }
  window.addEventListener("afterprint", cleanup)
  // let React flush the portal contents before the print dialog opens
  setTimeout(() => window.print(), 50)
}
