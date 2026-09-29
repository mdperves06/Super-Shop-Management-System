import { PageHeader, RequirePermission } from "@/components/shared/ui-parts"
import { ProductForm } from "@/features/products/product-form"

export const metadata = { title: "New product" }

export default function Page() {
  return (
    <RequirePermission any={["product.create"]}>
      <PageHeader back={{ href: "/products", label: "Products" }} title="Add product" description="Create a product, set its price and stock rules." />
      <ProductForm />
    </RequirePermission>
  )
}
