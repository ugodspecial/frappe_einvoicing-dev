# Doftwerks NRS E-Invoicing — Project Context

**Purpose:** the single, current source of truth for anyone (human or AI assistant) working on this app. Update it as phases complete and as the platform teaches us new rules.

**Last updated:** end of Phase 7 hardening (tests green, security pass done, credit-note flow proven live).

---

## 1. What this project is

A Frappe/ERPNext app, `doftwerks_nrs`, that transmits Sales Invoices to the Nigeria Revenue Service (NRS) through the **Doftwerks E-Invoice Access Point** platform. Intended for the Frappe Cloud Marketplace.

It is a port of a working Zoho Books integration that Doftwerks ran in production for three legal entities. Domain logic below was proven live — first in Zoho, now re-proven from this app (five live transmissions including a service-line invoice and a credit note).

**Owner:** Doftwerks West Africa Limited (technology practice of Stransact Chartered Accountants, Lagos). Doftwerks holds dual NRS accreditation as System Integrator and Access Point Provider.

**Platform base URL:** `https://einvoice.doftwerks.com`

---

## 2. NRS domain rules (all proven against the live platform)

Do not "correct" these from first principles.

### 2.1 Endpoints
- `POST /api/v1/einvoice/transmit` — submit an invoice.
- `PATCH /api/v1/einvoice/update-status/{irn}` — report payment settlement.
- `GET /api/v1/einvoice/lookup/{irn}` — current platform record for an IRN.
- `GET /api/v1/einvoice/download/{irn}` — download the invoice document.
- `POST /api/v1/einvoice/report` — post-payment VAT report (not yet wired).
- **Webhooks** — the platform POSTs status-change events to a registered URL (see 2.11).

Headers on every call: `x-client-id`, `x-client-secret`, `Content-Type: application/json`, `Accept: application/json`. Do **not** send `x-invoice-format` (legacy).

### 2.2 Invoice type codes — inverted vs UBL, and STRINGS
- `"381"` = Commercial Invoice, `"380"` = Credit Note, `"384"` = Debit Note.
- Anyone who knows UBL will map these backwards by instinct; they are correct as written.
- The platform 422s on integers: **send them as strings.**

### 2.3 IRN format
`{INVOICE_NUMBER cleaned to alphanumerics, uppercased}-{SERVICE_ID}-{YYYYMMDD of issue date}`
e.g. `ACCSINV202600001-F51EB213-20260803`. The second-to-last segment is the issuing entity's service ID — used as a tamper check when resolving entities from an IRN (webhook, payment push, reconciliation).

### 2.4 Invoice line shape (resolved via live 422s)
Each line: nested `item` and `price` objects; classification fields **flat on the line**:

```json
{
  "id": 1,
  "invoiced_quantity": 2,
  "line_extension_amount": 200.0,
  "item": {"name": "...", "description": "..."},
  "price": {"price_amount": 100.0, "base_quantity": 1, "price_unit": "NGN per 1"},
  "hsn_code": "9504.50", "product_category": "...",
  "isic_code": "", "service_category": "",
  "tax_category": [{"id": "STANDARD_VAT", "percent": 7.5}]
}
```

- The 422 error keys are `invoice_line.0.hsn_code` (not `...item.hsn_code`) — that is how we know classification is flat.
- **Goods:** `hsn_code` + `product_category` filled; ISIC pair `""`. **Services:** reverse. Unused pair is **empty strings, never null**.
- **HSN codes are format-validated: `0000.00`.** ISIC codes have no format rule (bare `6311` accepted).
- Goods/service determination is the explicit `nrs_is_service` checkbox on Item — never inferred from stock nature (a real Zoho misclassification bug).
- Lines also support `discount_rate/discount_amount/fee_rate/fee_amount` and `item.sellers_item_identification` (not yet used).

### 2.5 Tax
- `tax_category` on each line is an **array** of `{id, percent}`.
- `tax_total[0].tax_subtotal` accumulates per VAT group across lines.
- STANDARD_VAT = 7.5%; ZERO_VAT / EXEMPT_VAT = 0%. **REDUCED_VAT rate unconfirmed** — stubbed 0.0%; confirm before any reduced-rate item transmits.

### 2.6 billing_reference — mandatory for credit/debit notes
`[]` for standard invoices. For 380/384: `[{"irn": <original IRN>, "issue_date": "YYYY-MM-DD"}]`, resolved from the return's `return_against` → original's `nrs_irn`. Missing original IRN = pre-flight rejection.
Credit/debit notes transmit with **positive amounts** (ERPNext stores returns negative; direction is carried by the type code). Proven live: ACC-SINV-2026-00004 stored at the platform as 380 / +250,000.

### 2.7 Response handling — lifecycle-aware
- **Success:** `receipt_status` OR `irn` in `data`, OR the word **"signed"** in the message. `data` may be `[]` with the state only in the message — still success.
- `receipt_status`: 1→INITIATED, 2→SIGNED, 3→TRANSMITTING, 4→TRANSMITTED. No 5; payment is a separate axis.
- "Invoice is Signed but could not transmit. Accounting parties APP might be offline or busy" (code 55) is **SUCCESS** — write IRN + SIGNED; reconciliation/webhook advances it later.
- Genuine rejection → friendly translated error + REJECTED. Network failure → FAILED (nothing was rejected; retryable, and auto-retried daily).

### 2.8 Error behaviour
Codes seen: 0 success; 11 invalid credentials; 17 TAX ID mismatch; 23 IRN record not found; 40/422 validation; 55 signed-but-pending.
The platform now **batches validation errors** (422 with `data.errors` per-field dict — better than the one-per-response Zoho era). Deep NRS-level errors come as HTTP 400 with dotted paths (`invoicerequest.invoice.invoiceline[0].hsncode...`). Full pre-flight still matters: it catches everything before transmission in one pass.

### 2.9 Payment status quirks
- `update-status` moves PENDING → PARTIAL → PAID only. **PENDING is not a pushable target** (400 "Unable to process"). **PAID is terminal** — cannot be reverted via API; wrong PAID needs platform-side correction.
- A no-op returns code 0/success — verify the echoed `data.payment_status`, never trust the code.
- **update-status and lookup disagree**: after a successful PAID push, `lookup` still returns the original signed snapshot (`payment_status: PENDING`, original `payment_summary`). Raised with the platform team; until fixed, reconciliation's payment-drift warnings are expected noise.

### 2.10 Friendly error translation
Raw platform messages are developer-oriented; the app translates them to staff guidance via a regex map, **specific matches before general**. Hard-won details:
- The TIN needle must be word-bounded (`\btin\b`) — plain `"tin"` matches inside "Accoun**tin**g parties".
- tax-id-mismatch (supplier credentials) must outrank the customer-TIN match.
- **`accounting_customer_party.email` is mandatory** — pre-flight checks Customer `email_id`.
- Current needles, in order: billing_reference, duplicate, mismatch/tax id, street, city, email, lga, state, \btin\b, hsn, isic, category, not found, timeout/connection/unavailable/offline/busy.

### 2.11 Webhooks
The platform POSTs a JSON event on every status change of a transmitted invoice. Respond **HTTP 200** to acknowledge; anything else is retried. No query params; body only.
- Receiver: `https://{site}/api/method/doftwerks_nrs.einvoice.webhook` (guest, POST, rate-limited 120/min/IP).
- Register per environment in the platform portal Settings.
- Guards: IRN service-ID must match a configured entity; statuses outside 1–4 ignored; transitions forward-only (replays cannot downgrade); unknown IRN → 404 so the platform redelivers (covers the race where the event beats our DB commit).
- Webhooks are the **primary** status sync; daily reconciliation is the safety net.
- Event shape (confirmed live): flat JSON with eventType (TransmissionStatusEvent), irn, tenant, status (capitalized word, e.g. Transmitting/Transmitted), environment, timestamp, and a full invoice snapshot. The receiver reads top-level irn + status (word statuses upper-cased into the 1-4 rank map). Statuses outside the receipt axis (paid/rejected words) are acknowledged with 200 and ignored for now.
- price_unit note: other integrations send a UOM string (e.g. EA); our NGN per 1 is also accepted.
- TODO before marketplace: HMAC signature (platform-side change — we control both ends).

---

## 3. Multi-entity model

One ERPNext site, multiple Companies — one per legal entity. **Entity selection is `doc.company`**, never a per-invoice dropdown; no billing-entity field on Sales Invoice. Config rows (NRS Billing Entity child table in the NRS E-Invoice Settings single) link each Company to its credentials. Reverse resolution (webhook/payment/reconcile) uses the IRN's service-ID segment.

Credentials live **only** in the encrypted Password field — never in code, fixtures, logs, or commits.

---

## 4. Architecture

| Concern | Mechanism |
|---|---|
| Custom fields | Custom Field fixtures, filtered by dt + `nrs_` prefix (never a bare `fixtures = ["Custom Field"]`) |
| Transmit trigger | `doc_events` Sales Invoice `on_submit` (also `validate` for receipt type, `before_cancel` for the cancel block) |
| Payment push | `doc_events` Payment Entry `on_submit` + `on_cancel` |
| Status sync | Webhook receiver (primary) + `scheduler_events` daily reconciliation (safety net) |
| Secrets | `entity.get_password("client_secret")` at call time, straight into headers |
| Staff alerts | Notification Log entries created directly on REJECTED/FAILED — the Notification doctype's Value Change trigger does NOT fire for `db_set` writes |
| Retry | Whitelisted `retry_transmission` + form button (`doctype_js`) |
| List visibility | `doctype_list_js` wraps ERPNext's `get_indicator`: red "NRS REJECTED/FAILED" pills |
| QR | Platform's base64 PNG decoded into a File on `nrs_qr_image` (Attach Image) |
| Print | "NRS E-Invoice" Jinja print format fixture (QR + IRN verification block) |

All server logic lives in `doftwerks_nrs/einvoice.py`. The logger is lazy (`_logger()`) — `frappe.logger()` at module level opens files at import time and breaks imports from arbitrary CWDs.

Retry-friendliness rule: `customer_address` is stamped at creation and uneditable after submission, so the payload builder falls back to the customer's default address — fixing the Customer is always sufficient for a retry.

---

## 5. Data model

- **NRS E-Invoice Settings** (Single): enabled, base_url, auto_transmit_on_submit, billing_entities.
- **NRS Billing Entity** (child): company (Link→Company), client_id, client_secret (Password), business_id, service_id, supplier_tin/email/phone/business_description, supplier address fields (street/city/postal_zone/lga/state/country default NG).
- **Custom Fields** (fixtures): Customer — nrs_tin, nrs_state_code, nrs_lga_code, nrs_business_description, nrs_is_b2b. Item — nrs_hsn_code, nrs_product_category, nrs_tax_code, nrs_is_service. Sales Invoice — nrs_receipt_type, nrs_irn, nrs_receipt_status, nrs_error, nrs_qr_image, nrs_time (result fields read-only, no_copy, allow_on_submit).
- **Print Format** fixture: "NRS E-Invoice".

---

## 6. Testing

- Unit tests: `doftwerks_nrs/tests/test_einvoice.py` — 16 tests covering type codes, status derivation (incl. overpayment + credit-note signs), entity-by-IRN, receipt-type derivation, friendly-error ordering (incl. the word-boundary case), lifecycle response handling (code 55, full success, rejection), payload shape (nested item/price, flat classification, empty-string pairs, tax subtotals), pre-flight completeness, credit-note absolute amounts.
- Run: `bench --site <site> set-config allow_tests true` once, then `bench --site <site> run-tests --module doftwerks_nrs.tests.test_einvoice`.
- These tests already caught one real regression (backspace bytes in the TIN regex from a shell-escaping accident). Keep them in CI.
- Manual retry: `doftwerks_nrs.einvoice.retry_transmission("<invoice>")` — idempotent via the IRN guard.
- Debug an IRN: `doftwerks_nrs.einvoice.lookup_irn("<irn>")`.

---

## 7. Phase status

- ✅ **Phases 0–4** — environment, scaffold, doctypes, fixtures, transmit engine. First live transmission 2026-08-03.
- ✅ **Phase 5** — payment push (PAID accepted live), cancel policy (blocked with credit-note guidance), credit/debit notes (live 380 with billing_reference, absolute amounts, auto receipt type).
- ✅ **Phase 6** — daily reconciliation (advanced two invoices live), webhook receiver, Notification Log alerts, print format, retry button, list-view indicator.
- ✅ **Phase 7 (code)** — 16 unit tests green; security pass (secrets only ever flow into headers; nothing sensitive logged; webhook rate-limited). **Pending: CI green on push, multi-version check.**
- 🔲 **Phase 8** — marketplace: README/docs, logo (≥200×200, no text), screenshots, description, developer account, versioned release, review.

---

## 8. Open items

- **REDUCED_VAT rate** — confirm with NRS before any reduced-rate item transmits.
- **`environment` field** — decorative; either wire Sandbox/Production base URLs or drop it.
- **Webhook registration** — needs a publicly reachable site (or tunnel) per environment; then HMAC signing (platform-side) before marketplace release.
- **update-status vs lookup payment disagreement** (§2.9) — platform team.
- **Platform record inconsistency** (lookup code 23 for signed invoices) — reconciliation logs these as `missing_at_platform`; platform team.
- **`report` endpoint** — post-payment VAT report not yet wired.

---

## 9. Working conventions

- WSL2 Ubuntu 24.04, Frappe v15, site `dev.localhost`. Start each session: `sudo service mariadb start && sudo service redis-server start`; `bench start` in its own terminal.
- Secrets only in encrypted Password fields. Never commit/log/hardcode a `cli_live_` secret. The marketplace repo is public.
- After each phase: verify in the browser, then commit with a clear message.
- Client-facing language: "NRS", never "FIRS"; the platform is the Doftwerks E-Invoice Access Point.
