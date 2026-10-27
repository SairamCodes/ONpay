# Payment integration assessment

## Current ONPay behavior

The current payment adapter constructs a standard `upi://pay` intent with the agreed amount, scanned payee VPA, exchange reference, and INR currency. The student reviews those details and chooses to open the phone's supported UPI app chooser. ONPay does not collect a UPI PIN. Returning to the site moves the record to **Verification pending**; it does not count as settlement proof.

The cash handover is stored separately from the digital payment. The server only marks an exchange successful after both participants confirm the cash handover and an operator has checked an independent bank record through the separately authenticated reconciliation endpoint. That endpoint is disabled until `RECONCILIATION_TOKEN` is configured. It awards points and creates a friend relationship idempotently after success.

## YouPI-PG compatibility

The current [YouPI-PG README](https://github.com/youpi-pg/YouPI-PG) and [architecture](https://github.com/youpi-pg/YouPI-PG/blob/main/ARCHITECTURE.md) describe a self-hosted merchant collection checkout with one receiving merchant VPA, a merchant order ID, amount-based payment sessions, UPI app deep links, and bank alert observers. Its [merchant guide](https://github.com/youpi-pg/YouPI-PG/blob/main/docs/MERCHANT_INTEGRATION.md) creates merchant payments through `POST /api/v1/payments` and reports outcomes through signed webhooks. Its [OpenAPI contract](https://github.com/youpi-pg/YouPI-PG/blob/main/openapi.yaml) exposes merchant payment creation, status lookup, and cancellation.

That checkout is not the ONPay exchange model: ONPay needs a payer to pay the specific student who is providing cash, while YouPI-PG's documented flow collects into the configured merchant receiving account. Its amount-matching observer and webhook can be useful for a controlled merchant experiment, but do not independently prove that a particular student received funds in an arbitrary student-to-student exchange. The repository labels itself experimental and not bank/NPCI approved, audited, or production-ready. ONPay therefore does not use it to initiate or mark student payments successful.

`YouPIMerchantAdapter` remains an explicit integration boundary and refuses arbitrary student recipients. The signed `/api/webhooks/youpi` endpoint, when configured, verifies the raw-body HMAC, delivery ID, and amount, then records **Verification pending** for manual reconciliation. It never transitions an exchange to success.

## Requirements before real-money operation

- A supported, authorized provider for the intended person-to-person transaction type, with server-side settlement confirmation tied to the correct payee, amount, and reference.
- Provider credentials and callback configuration stored only on the server.
- Independent reconciliation, duplicate and delayed-event handling, refund/dispute procedures, and security review.
- Qualified advice on applicable Indian payment, consumer, privacy, and UPI requirements.

This assessment is technical product documentation, not a legal or compliance opinion.
