import type { Metadata, Viewport } from "next"
import { Geist_Mono, Inter, Noto_Sans_Bengali } from "next/font/google"

import { Providers } from "@/components/providers"

import "./globals.css"

const inter = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" })
const bengali = Noto_Sans_Bengali({ variable: "--font-bengali", subsets: ["bengali"], display: "swap" })
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] })

export const metadata: Metadata = {
  title: { default: "Super Shop", template: "%s · Super Shop" },
  description: "Super shop management: POS, inventory, purchasing, customers and reports.",
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${bengali.variable} ${mono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
