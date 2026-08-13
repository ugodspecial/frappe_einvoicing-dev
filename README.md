<div align="center">
	<img src="https://raw.githubusercontent.com/doftwerks-dev/frappe_einvoicing/main/doftwerks_nrs/public/images/nrs-einvoice-logo.png" height="120" alt="Doftwerks">
	<h1>Doftwerks NRS E-Invoicing</h1>
	<p>NRS-compliant e-invoicing for ERPNext, via the Doftwerks E-Invoice Access Point.</p>
</div>

Transmit Sales Invoices to the **Nigeria Revenue Service (NRS)** directly from ERPNext. On submission, invoices are validated, signed, and transmitted through the Doftwerks E-Invoice Access Point — an NRS-accredited platform — and the returned IRN, receipt status, and verification QR code are written back onto the invoice.

## Features

- **Automatic transmission on submit** — with a full pre-flight check that reports *all* data problems at once (customer TIN, state/LGA codes, address, email, item HSN/ISIC codes) in plain language, before anything is sent.
- **Multi-entity by Company** — each ERPNext Company maps to its own NRS credentials and supplier profile. The entity is determined by the invoice's Company; there is nothing to select and nothing to get wrong.
- **Credit and debit notes** — returns transmit as NRS credit/debit notes automatically, referencing the original invoice's IRN.
- **IRN, status, and QR code on the invoice** — plus a ready-made "NRS E-Invoice" print format with the verification QR.
- **Retry from the form** — rejected or failed transmissions show a retry button; rejected invoices are flagged red in the invoice list.
- **Payment status sync** — payments and cancellations push settlement status (partial/paid) to NRS automatically.
- **Webhook + daily reconciliation** — statuses stay in sync via platform webhooks, with a daily lookup sweep as the safety net; connectivity failures retry automatically.
- **Problem notifications** — Accounts Managers get bell notifications when a transmission is rejected or fails.
- **Built-in code lookups** - HSN/ISIC and State/LGA lookup tools open right from the Item and Customer forms, and from the NRS E-Invoicing workspace.
- **Encrypted credentials** — client secrets are stored in Frappe's encrypted Password fields, never in code or logs.

## Requirements

- Frappe / ERPNext **version 15**
- **Doftwerks E-Invoice Access Point credentials** for each legal entity (Client ID and Client Secret). The app cannot transmit without them — to get onboarded, contact [support@doftwerks.com](mailto:support@doftwerks.com), call +234 708 063 9999, or visit [doftwerks.com](https://doftwerks.com).

## Installation

**Frappe Cloud:** install from the Marketplace, or add this repository as a custom app on your bench.

**Self-hosted:**

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/doftwerks-dev/frappe_einvoicing --branch main
bench --site yoursite.com install-app doftwerks_nrs
```

## Setup

1. Open **NRS E-Invoice Settings** (search bar, the **NRS E-Invoicing** workspace in the sidebar, or the Apps screen tile).
2. Under **Billing Entities**, add a row per Company: select the Company and enter the credentials and supplier details issued by Doftwerks.
3. Click **Test Connection** to verify the credentials against the platform.
4. On each **Customer** (Tax tab): set NRS TIN, State Code, LGA Code, and mark B2B customers. An email address and a billing address with street and city are required by NRS.
5. On each **Item** (Tax tab): set the HSN code (goods, `0000.00` format) or ISIC code (services), the product/service category, the NRS tax code, and tick *Is Service* for service items.
6. Tick **Enabled** (and leave **Auto Transmit on Submit** on) and save.
7. Ask Doftwerks to register your site's webhook URL so statuses update in real time - the settings page shows it with a **Copy Webhook URL** button:
   `https://yoursite.com/api/method/doftwerks_nrs.einvoice.webhook`

Submit a Sales Invoice — the NRS E-Invoicing section on the invoice shows the IRN, receipt status, and QR code. If anything is rejected, the NRS Error field explains exactly what to fix, and a **Retry NRS Transmission** button appears once you have.

## How it works

| Event | What happens |
|---|---|
| Sales Invoice submitted | Pre-flight validation → transmit → IRN + status + QR written back. Failures never block submission. |
| Return / Credit Note submitted | Transmits as an NRS credit note referencing the original IRN. |
| Payment Entry submitted / cancelled | Settlement status (PARTIAL / PAID) pushed to NRS. |
| Invoice with an IRN cancelled | Blocked — issue a Credit Note instead (NRS records cannot be cancelled). |
| Platform status change | Webhook updates the invoice; a daily reconciliation sweep catches anything missed and retries connectivity failures. |

## Development

```bash
bench --site yoursite.com set-config allow_tests true
bench --site yoursite.com run-tests --app doftwerks_nrs
```

Domain rules, platform behaviour, and architecture notes live in [docs/CONTEXT.md](docs/CONTEXT.md). This app uses `pre-commit` (ruff, eslint, prettier, pyupgrade) — enable it with `pre-commit install`.

## License

MIT — see [license.txt](license.txt).

---

Built and maintained by [Doftwerks West Africa Limited](https://doftwerks.com), the technology practice of Stransact Chartered Accountants. Doftwerks holds dual NRS accreditation as a System Integrator and Access Point Provider.
