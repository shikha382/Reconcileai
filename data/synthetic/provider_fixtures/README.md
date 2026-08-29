# Provider fixtures — SYNTHETIC FIXTURE

Every file in this directory is **entirely synthetic**. No real customer, merchant, payment, or account data is present anywhere here — every ID, amount, name, and reference below was invented for this project. Field *shapes* are modeled on Razorpay's own public API documentation (payment/settlement/refund entities) and on generic bank-statement/order-management export conventions, so the adapter (`backend/app/adapters/`) is exercised against realistic structure — never on real values.

Three linked scenarios, sharing external IDs across files exactly the way a real provider's data would link:

1. `RAZ0000001AA` — a clean UPI payment, fully settled, bank-confirmed. No refund.
2. `RAZ0000002BB` — a payment with a partial refund afterward.
3. `RAZ0000003CC` — a second clean UPI payment (proves the adapter/pipeline handles more than one record correctly, including pagination when `PROVIDER_MAX_PAGE_SIZE` is set below 3).

See `docs/provider-adapters.md` for the full field-by-field mapping table.
