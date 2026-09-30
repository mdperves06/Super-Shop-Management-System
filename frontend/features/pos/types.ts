export interface CartPayload {
  items: { product_id: number; quantity: number; discount_type?: "PERCENT" | "FIXED"; discount_value: number }[]
  customer_id: number | null
  invoice_discount_type?: "PERCENT" | "FIXED"
  invoice_discount_value: number
  discount_request_id?: number
}
