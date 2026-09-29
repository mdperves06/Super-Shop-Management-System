import { RequirePermission } from "@/components/shared/ui-parts"
import { BarcodeLabelsPage } from "@/features/products/barcode-labels"

export const metadata = { title: "Barcode labels" }

export default function Page() {
  return <RequirePermission any={["product.read"]}><BarcodeLabelsPage /></RequirePermission>
}
