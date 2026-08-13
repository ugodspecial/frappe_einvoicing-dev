# Copyright (c) 2026, Doftwerks West Africa Limited and contributors
# For license information, please see license.txt

"""NRS e-invoice transmission for Sales Invoice.

Wired to Sales Invoice on_submit via hooks.doc_events. All writes to the
(already submitted) invoice go through db_set.
"""

import json
import re
from base64 import b64decode

import frappe
import requests
from frappe.rate_limiter import rate_limit
from frappe.contacts.doctype.address.address import get_default_address
from frappe.utils import cint, cstr, flt, getdate, now, now_datetime, strip_html_tags

SETTINGS_DOCTYPE = "NRS E-Invoice Settings"
REQUEST_TIMEOUT = 30

# NRS expects these codes. They are intentionally the reverse of UBL-1001
# (where 380 = Invoice and 381 = Credit Note) — do not "correct" them.
# The platform requires them as strings (422: "must be a string").
INVOICE_TYPE_CODES = {
	"Invoice": "381",
	"Credit Note": "380",
	"Debit Note": "384",
}

RECEIPT_STATUS_LABELS = {
	1: "INITIATED",
	2: "SIGNED",
	3: "TRANSMITTING",
	4: "TRANSMITTED",
}

PAYMENT_STATUS = {
	"Paid": "PAID",
	"Partly Paid": "PARTIAL",
}

# VAT percent per NRS tax code. REDUCED_VAT has no published rate yet —
# confirm with NRS before invoicing reduced-rate items.
TAX_RATES = {
	"STANDARD_VAT": 7.5,
	"REDUCED_VAT": 0.0,
	"ZERO_VAT": 0.0,
	"EXEMPT_VAT": 0.0,
}

OFFLINE_MESSAGE = (
	"The NRS e-invoicing platform could not be reached. "
	"The invoice was NOT transmitted - retry once the platform is back online."
)

# (regex needle searched in the platform's error message, plain guidance) - matched top to
# bottom, so keep specific needles before general ones.
SUPPLIER_TIN_MISMATCH_MESSAGE = (
	"NRS reports a TAX ID mismatch: the Supplier TIN configured for this "
	"Company does not match the TIN registered to these NRS credentials. "
	"Check the billing entity row in NRS E-Invoice Settings."
)

ITEM_CLASSIFICATION_MESSAGE = (
	"NRS rejected an item's classification. Goods need an HSN code in "
	"0000.00 format, services an ISIC code. "
	"Check the NRS fields on the invoice's Item(s) and retry."
)

FRIENDLY_ERRORS = [
	(
		"billing_reference",
		"The original invoice for this credit/debit note has not been transmitted "
		"to NRS yet. Transmit the original invoice first, then retry.",
	),
	(
		"duplicate",
		"NRS reports this invoice was already transmitted. Check the earlier "
		"submission before retrying.",
	),
	# supplier credential mismatch (error 17) must outrank the generic "tin" match
	("mismatch", SUPPLIER_TIN_MISMATCH_MESSAGE),
	("tax id", SUPPLIER_TIN_MISMATCH_MESSAGE),
	(
		"street",
		"NRS rejected the customer's address: the street is missing or invalid. "
		"Fix Address Line 1 on the customer's address and retry.",
	),
	(
		"city",
		"NRS rejected the customer's address: the city is missing or invalid. "
		"Fix the City on the customer's address and retry.",
	),
	(
		"email",
		"NRS rejected the customer email address. Set a valid Email ID on the "
		"Customer and retry.",
	),
	(
		"lga",
		"NRS rejected the customer's LGA code. Set NRS LGA Code on the Customer "
		"(Tax tab) and retry.",
	),
	(
		"state",
		"NRS rejected the customer's state code. Set NRS State Code on the "
		"Customer (Tax tab) and retry.",
	),
	(
		r"\btin\b",
		"NRS rejected the customer's TIN. Check the NRS TIN on the Customer "
		"(Tax tab) and retry.",
	),
	("hsn", ITEM_CLASSIFICATION_MESSAGE),
	("isic", ITEM_CLASSIFICATION_MESSAGE),
	("category", ITEM_CLASSIFICATION_MESSAGE),
	(
		"not found",
		"NRS has no record of this IRN yet. The invoice may not have been "
		"transmitted, or the platform's record is delayed - check the "
		"transmission status and retry later.",
	),
	("timed out", OFFLINE_MESSAGE),
	("timeout", OFFLINE_MESSAGE),
	("connection", OFFLINE_MESSAGE),
	("unavailable", OFFLINE_MESSAGE),
	("offline", OFFLINE_MESSAGE),
	("busy", OFFLINE_MESSAGE),
]

def _logger():
	return frappe.logger("nrs_einvoice")


def transmit_on_submit(doc, method=None):
	"""Sales Invoice on_submit hook. Never blocks submission."""
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	if not settings.enabled or not settings.auto_transmit_on_submit:
		return

	try:
		transmit_invoice(doc, settings)
	except Exception:
		frappe.log_error(
			title=f"NRS transmission failed for {doc.name}",
			message=frappe.get_traceback(),
		)


def transmit_invoice(doc, settings=None):
	settings = settings or frappe.get_single(SETTINGS_DOCTYPE)

	if doc.nrs_irn:
		_logger().info(f"{doc.name}: already transmitted (IRN {doc.nrs_irn}), skipping")
		return

	entity = _find_billing_entity(settings, doc.company)
	if not entity:
		_logger().info(f"{doc.name}: company {doc.company} has no NRS billing entity, skipping")
		return

	errors = []
	payload = build_payload(doc, entity, errors)
	if errors:
		joined = "\n".join(errors)
		_write_status(doc, "REJECTED", joined)
		frappe.log_error(title=f"NRS pre-flight failed for {doc.name}", message=joined)
		return

	url = f"{cstr(settings.base_url).rstrip('/')}/api/v1/einvoice/transmit"
	headers = {
		"x-client-id": entity.client_id,
		"x-client-secret": entity.get_password("client_secret"),
		"Content-Type": "application/json",
		"Accept": "application/json",
	}

	try:
		response = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
	except requests.exceptions.RequestException:
		frappe.log_error(
			title=f"NRS platform unreachable for {doc.name}",
			message=frappe.get_traceback(),
		)
		_write_status(doc, "FAILED", OFFLINE_MESSAGE)
		return

	_handle_response(doc, payload, response)


def build_payload(doc, entity, errors=None):
	"""Build the NRS transmit payload. Data problems are appended to `errors`."""
	if errors is None:
		errors = []

	customer = frappe.get_doc("Customer", doc.customer)
	# customer_address is stamped at creation and cannot be edited on a
	# submitted invoice - fall back to the customer's default address so
	# fixing the Customer is enough for a retry to succeed
	address_name = doc.customer_address or get_default_address("Customer", doc.customer)
	address = frappe.get_doc("Address", address_name) if address_name else None
	is_b2b = cint(customer.get("nrs_is_b2b"))
	issue_date = getdate(doc.posting_date)
	receipt_type = cstr(doc.get("nrs_receipt_type")) or "Invoice"

	street = cstr(address.address_line1).strip() if address else ""
	city = cstr(address.city).strip() if address else ""
	if not street:
		errors.append(
			"Customer address is missing a street. Set Address Line 1 on the "
			"customer's address."
		)
	if not city:
		errors.append("Customer address is missing a city. Set City on the customer's address.")

	if is_b2b:
		if not customer.get("nrs_tin"):
			errors.append("B2B customer requires an NRS TIN. Set it on the Customer (Tax tab).")
		if not customer.get("nrs_state_code"):
			errors.append("B2B customer requires an NRS State Code. Set it on the Customer (Tax tab).")
		if not customer.get("nrs_lga_code"):
			errors.append("B2B customer requires an NRS LGA Code. Set it on the Customer (Tax tab).")

	if not customer.get("email_id"):
		errors.append("Customer email is required by NRS. Set an Email ID on the Customer.")

	lines, tax_groups = _build_lines(doc, errors)
	total_tax = flt(sum(g["tax_amount"] for g in tax_groups.values()), 2)

	return {
		"business_id": entity.business_id,
		"invoice_number": doc.name,
		"irn": "{0}-{1}-{2}".format(
			re.sub(r"[^A-Za-z0-9]", "", cstr(doc.name)).upper(),
			entity.service_id,
			issue_date.strftime("%Y%m%d"),
		),
		"invoice_type_code": INVOICE_TYPE_CODES.get(receipt_type, INVOICE_TYPE_CODES["Invoice"]),
		"payment_status": PAYMENT_STATUS.get(cstr(doc.status), "PENDING"),
		"invoice_kind": "B2B" if is_b2b else "B2C",
		"issue_date": str(issue_date),
		"issue_time": now_datetime().strftime("%H:%M:%S"),
		"due_date": str(doc.due_date or issue_date),
		"tax_point_date": str(issue_date),
		"document_currency_code": doc.currency,
		"tax_currency_code": doc.currency,
		"accounting_supplier_party": {
			"party_name": entity.company,
			"tin": entity.supplier_tin,
			"email": entity.supplier_email or "",
			"telephone": entity.supplier_phone or "",
			"business_description": entity.supplier_business_description or "",
			"postal_address": {
				"street_name": entity.supplier_street or "",
				"city_name": entity.supplier_city or "",
				"postal_zone": entity.supplier_postal_zone or "",
				"lga": entity.supplier_lga or "",
				"state": entity.supplier_state or "",
				"country": entity.supplier_country or "NG",
			},
		},
		"accounting_customer_party": {
			"party_name": customer.customer_name or doc.customer_name,
			"tin": customer.get("nrs_tin") or "",
			"email": customer.get("email_id") or "",
			"telephone": customer.get("mobile_no") or "",
			"business_description": customer.get("nrs_business_description") or "",
			"postal_address": {
				"street_name": street,
				"city_name": city or "Lagos",
				"postal_zone": cstr(address.pincode).strip() if address else "",
				"lga": customer.get("nrs_lga_code") or "",
				"state": customer.get("nrs_state_code") or "",
				"country": _country_code(address),
			},
		},
		"invoice_line": lines,
		"tax_total": [
			{
				"tax_amount": total_tax,
				"tax_subtotal": [
					{
						"taxable_amount": group["taxable_amount"],
						"tax_amount": group["tax_amount"],
						"tax_category": {"id": code, "percent": TAX_RATES.get(code, 0.0)},
					}
					for code, group in tax_groups.items()
				],
			}
		],
		"legal_monetary_total": {
			"line_extension_amount": flt(sum(line["line_extension_amount"] for line in lines), 2),
			"tax_exclusive_amount": _doc_amount(doc, doc.net_total),
			"tax_inclusive_amount": _doc_amount(doc, doc.grand_total),
			"payable_amount": _doc_amount(doc, doc.grand_total),
		},
		"payment_summary": _build_payment_summary(doc),
		"billing_reference": _build_billing_reference(doc, receipt_type, errors),
	}


def _build_lines(doc, errors):
	lines = []
	tax_groups = {}
	absolute = cint(doc.get("is_return"))

	for row in doc.items:
		item = frappe.get_cached_doc("Item", row.item_code) if row.item_code else None
		code = cstr(item.get("nrs_hsn_code")).strip() if item else ""
		category = cstr(item.get("nrs_product_category")).strip() if item else ""
		tax_code = (cstr(item.get("nrs_tax_code")) if item else "") or "STANDARD_VAT"
		is_service = cint(item.get("nrs_is_service")) if item else 0

		if not code:
			errors.append(
				f"Item {row.item_code or row.item_name} is missing an NRS HSN/ISIC code. "
				"Set it on the Item (Tax tab)."
			)

		net_amount = flt(row.net_amount, 2)
		if absolute:
			net_amount = abs(net_amount)
		rate = TAX_RATES.get(tax_code, 0.0)
		group = tax_groups.setdefault(tax_code, {"taxable_amount": 0.0, "tax_amount": 0.0})
		group["taxable_amount"] = flt(group["taxable_amount"] + net_amount, 2)
		group["tax_amount"] = flt(group["tax_amount"] + net_amount * rate / 100, 2)

		lines.append(
			{
				"id": row.idx,
				"invoiced_quantity": abs(flt(row.qty)) if absolute else flt(row.qty),
				"line_extension_amount": net_amount,
				# nested item/price objects are required (platform 422s on flat)
				"item": {
					"name": row.item_name,
					"description": strip_html_tags(cstr(row.description)).strip() or row.item_name,
				},
				# classification is flat on the line: the 422 keys are
				# invoice_line.0.hsn_code, not ...item.hsn_code. Goods use HSN,
				# services use ISIC; unused pair = empty strings, never null.
				"hsn_code": "" if is_service else code,
				"product_category": "" if is_service else category,
				"isic_code": code if is_service else "",
				"service_category": category if is_service else "",
				"price": {
					"price_amount": flt(row.rate, 2),
					"base_quantity": 1,
					"price_unit": f"{doc.currency} per 1",
				},
				"tax_category": [{"id": tax_code, "percent": rate}],
			}
		)

	return lines, tax_groups


def _build_payment_summary(doc):
	grand_total = _doc_amount(doc, doc.grand_total)
	outstanding = _doc_amount(doc, doc.outstanding_amount)
	total_paid = flt(grand_total - outstanding, 2)
	return {
		"total_paid": total_paid,
		"balance_due": outstanding,
		"payment_count": 1 if total_paid > 0 else 0,
	}


def _build_billing_reference(doc, receipt_type, errors):
	if receipt_type == "Invoice":
		return []

	original_irn = None
	original_date = None
	if doc.get("return_against"):
		original_irn, original_date = frappe.db.get_value(
			"Sales Invoice", doc.return_against, ["nrs_irn", "posting_date"]
		) or (None, None)

	if not original_irn:
		errors.append(
			f"This {receipt_type.lower()} references no transmitted original invoice. "
			"Transmit the original invoice to NRS first (Return Against must point to "
			"an invoice with an NRS IRN)."
		)
		return []

	return [{"irn": original_irn, "issue_date": str(original_date)}]


def _handle_response(doc, payload, response):
	try:
		body = response.json()
	except ValueError:
		body = {}

	message = cstr(body.get("message"))
	data = body.get("data")
	if not isinstance(data, dict):
		# platform sometimes returns data as [] with the state only in the message
		data = {}

	signed_in_message = "signed" in message.lower()
	success = bool(data.get("irn") or data.get("receipt_status")) or signed_in_message

	if not success:
		raw = message or cstr(response.text)[:500] or f"HTTP {response.status_code}"
		_write_status(doc, "REJECTED", _friendly_error(raw))
		frappe.log_error(
			title=f"NRS rejected {doc.name}",
			message=f"HTTP {response.status_code}\n{cstr(response.text)[:5000]}",
		)
		return

	status_label = RECEIPT_STATUS_LABELS.get(cint(data.get("receipt_status")))
	if not status_label:
		status_label = "SIGNED" if signed_in_message else "TRANSMITTED"

	irn = data.get("irn") or payload["irn"]
	doc.db_set("nrs_irn", irn, update_modified=False)
	doc.db_set("nrs_receipt_status", status_label, update_modified=False)
	doc.db_set("nrs_time", now(), update_modified=False)
	doc.db_set("nrs_error", "", update_modified=False)
	if data.get("qr_code"):
		_attach_qr_image(doc, data["qr_code"])

	_logger().info(f"{doc.name}: transmitted to NRS, irn={irn}, status={status_label}")


def _attach_qr_image(doc, qr_base64):
	try:
		content = b64decode(qr_base64)
	except Exception:
		frappe.log_error(
			title=f"NRS QR decode failed for {doc.name}",
			message=frappe.get_traceback(),
		)
		return

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"NRS-QR-{doc.name}.png",
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"attached_to_field": "nrs_qr_image",
			"content": content,
		}
	).insert(ignore_permissions=True)
	doc.db_set("nrs_qr_image", file_doc.file_url, update_modified=False)


def _find_billing_entity(settings, company):
	for row in settings.billing_entities:
		if row.company == company:
			return row
	return None


def _country_code(address):
	if address and address.country:
		code = frappe.db.get_value("Country", address.country, "code")
		if code:
			return code.upper()
	return "NG"


def _friendly_error(raw):
	low = cstr(raw).lower()
	for needle, friendly in FRIENDLY_ERRORS:
		if re.search(needle, low):
			return friendly
	return cstr(raw)


def _write_status(doc, status, error):
	doc.db_set("nrs_receipt_status", status, update_modified=False)
	doc.db_set("nrs_error", error, update_modified=False)
	if status in ("REJECTED", "FAILED"):
		try:
			_notify_problem(doc, status, error)
		except Exception:
			frappe.log_error(
				title=f"NRS notification failed for {doc.name}",
				message=frappe.get_traceback(),
			)


@frappe.whitelist()
def retry_transmission(name):
	"""Manual retry entrypoint (console, bench execute, or a future button)."""
	doc = frappe.get_doc("Sales Invoice", name)
	doc.check_permission("submit")
	transmit_invoice(doc)
	doc.reload()
	return {
		"irn": doc.nrs_irn,
		"receipt_status": doc.nrs_receipt_status,
		"error": doc.nrs_error,
	}


RECEIPT_STATUS_RANK = {label: rank for rank, label in RECEIPT_STATUS_LABELS.items()}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=120, seconds=60)
def webhook():
	"""Status-change events pushed by the Access Point platform.

	The platform only needs an HTTP 200 to acknowledge delivery; any other
	code makes it retry later. Configure the URL in the platform portal as:
	https://{site}/api/method/doftwerks_nrs.einvoice.webhook
	"""
	try:
		payload = json.loads(frappe.request.data or b"{}")
	except ValueError:
		frappe.local.response["http_status_code"] = 400
		return {"status": "error", "reason": "invalid json"}

	# acknowledge non-status events (e.g. the portal test POST on saving the
	# webhook URL) without touching any invoice
	event_type = cstr(payload.get("eventType"))
	if event_type and event_type != "TransmissionStatusEvent":
		return {"status": "ok", "detail": f"event type {event_type} acknowledged"}

	data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
	irn = cstr(data.get("irn")).strip()
	if not irn:
		frappe.local.response["http_status_code"] = 400
		return {"status": "error", "reason": "no irn"}

	# The second-to-last IRN segment is the issuing entity's service id —
	# only accept events for entities configured on this site.
	parts = irn.split("-")
	service_id = parts[-2] if len(parts) >= 3 else None
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	if not service_id or not any(row.service_id == service_id for row in settings.billing_entities):
		frappe.local.response["http_status_code"] = 404
		return {"status": "ignored", "reason": "unknown service id"}

	name = frappe.db.get_value("Sales Invoice", {"nrs_irn": irn}, "name")
	if not name:
		# The event can arrive before our transmit transaction commits the
		# IRN; a non-200 makes the platform redeliver later.
		frappe.local.response["http_status_code"] = 404
		return {"status": "ignored", "reason": "no invoice with this irn"}

	status_label = RECEIPT_STATUS_LABELS.get(cint(data.get("receipt_status")))
	if not status_label:
		raw = cstr(data.get("receipt_status") or data.get("status")).strip().upper()
		if raw in RECEIPT_STATUS_RANK:
			status_label = raw
	if not status_label:
		return {"status": "ok", "detail": "no recognisable receipt_status; ignored"}

	# Forward-only: never downgrade on out-of-order delivery. REJECTED/FAILED
	# and empty rank as 0, so a real lifecycle status always overrides them.
	current = cstr(frappe.db.get_value("Sales Invoice", name, "nrs_receipt_status"))
	if RECEIPT_STATUS_RANK.get(status_label, 0) > RECEIPT_STATUS_RANK.get(current, 0):
		frappe.db.set_value(
			"Sales Invoice",
			name,
			{"nrs_receipt_status": status_label, "nrs_error": ""},
			update_modified=False,
		)
		_logger().info(f"webhook: {name} {current or 'NONE'} -> {status_label}")
		return {"status": "ok", "updated": status_label}

	return {"status": "ok", "detail": "no change"}


def _doc_amount(doc, value):
	"""Credit/debit notes are transmitted with positive amounts (ERPNext
	stores returns negative); direction is carried by invoice_type_code."""
	amount = flt(value, 2)
	return abs(amount) if cint(doc.get("is_return")) else amount


def set_receipt_type(doc, method=None):
	"""Sales Invoice validate hook: derive the NRS receipt type from
	ERPNext's own return/debit flags so staff never set it by hand."""
	if cint(doc.get("is_return")):
		doc.nrs_receipt_type = "Credit Note"
	elif cint(doc.get("is_debit_note")):
		doc.nrs_receipt_type = "Debit Note"
	elif not doc.get("nrs_receipt_type"):
		doc.nrs_receipt_type = "Invoice"


def block_cancel_after_transmit(doc, method=None):
	"""Sales Invoice before_cancel hook: a transmitted invoice is a fiscal
	record at NRS with no cancel API — the compliant reversal is a Credit
	Note (Return), never an ERPNext cancel."""
	if doc.get("nrs_irn"):
		frappe.throw(
			frappe._(
				"This invoice was transmitted to NRS (IRN {0}) and cannot be "
				"cancelled. Issue a Credit Note (Create > Return / Credit Note) "
				"to reverse it."
			).format(doc.nrs_irn),
			title=frappe._("Transmitted to NRS"),
		)


def push_payment_status_on_submit(doc, method=None):
	"""Payment Entry on_submit/on_cancel hook. Recomputes each referenced
	invoice's settlement state from its fresh outstanding. Never blocks the
	payment document."""
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	if not settings.enabled:
		return

	try:
		for ref in doc.get("references") or []:
			if ref.reference_doctype == "Sales Invoice":
				push_payment_status(ref.reference_name, settings)
	except Exception:
		frappe.log_error(
			title=f"NRS payment status push failed for {doc.name}",
			message=frappe.get_traceback(),
		)


def push_payment_status(invoice_name, settings=None):
	settings = settings or frappe.get_single(SETTINGS_DOCTYPE)
	inv = frappe.db.get_value(
		"Sales Invoice",
		invoice_name,
		["name", "nrs_irn", "grand_total", "outstanding_amount", "docstatus"],
		as_dict=True,
	)
	if not inv or not inv.nrs_irn or inv.docstatus != 1:
		return {"skipped": "no IRN or not submitted"}

	entity = _find_entity_by_irn(settings, inv.nrs_irn)
	if not entity:
		_logger().info(f"{invoice_name}: no entity for IRN {inv.nrs_irn}, skipping payment push")
		return {"skipped": "no entity for IRN"}

	payment_status = _derive_payment_status(inv.outstanding_amount, inv.grand_total)
	if payment_status == "PENDING":
		# PENDING is the initial state at NRS; update-status only moves
		# PENDING -> PARTIAL -> PAID and 400s on a no-op push
		_logger().info(f"{invoice_name}: derived PENDING, nothing to push")
		return {"skipped": "PENDING is not a pushable target"}
	url = f"{cstr(settings.base_url).rstrip('/')}/api/v1/einvoice/update-status/{inv.nrs_irn}"
	headers = {
		"x-client-id": entity.client_id,
		"x-client-secret": entity.get_password("client_secret"),
		"Content-Type": "application/json",
		"Accept": "application/json",
	}

	try:
		response = requests.patch(
			url, json={"payment_status": payment_status}, headers=headers, timeout=REQUEST_TIMEOUT
		)
	except requests.exceptions.RequestException:
		frappe.log_error(
			title=f"NRS payment status push unreachable for {invoice_name}",
			message=frappe.get_traceback(),
		)
		return {"error": "unreachable"}

	try:
		body = response.json()
	except ValueError:
		body = {}
	if not response.ok:
		frappe.log_error(
			title=f"NRS payment status push rejected for {invoice_name}",
			message=f"HTTP {response.status_code}\n{cstr(response.text)[:5000]}",
		)
		return {"error": f"HTTP {response.status_code}", "message": cstr(body.get("message"))}

	data = body.get("data") if isinstance(body.get("data"), dict) else {}
	echoed = cstr(data.get("payment_status")).upper()

	# Platform quirk: a no-op also answers code 0 / success. Trust the echoed
	# payment_status, not the code — "paid" is terminal at NRS and a refused
	# downgrade needs platform-side correction.
	if echoed and echoed != payment_status:
		frappe.log_error(
			title=f"NRS payment status not updated for {invoice_name}",
			message=(
				f"Requested {payment_status} but the platform kept {echoed}. "
				"PAID is terminal at NRS and cannot be reverted via the API; "
				"platform-side correction is required."
			),
		)
		return {"pushed": payment_status, "platform_kept": echoed}

	_logger().info(f"{invoice_name}: NRS payment status -> {payment_status}")
	return {"pushed": payment_status, "http": response.status_code, "message": cstr(body.get("message"))}


def _derive_payment_status(outstanding, grand_total):
	outstanding = flt(outstanding)
	grand_total = flt(grand_total)
	# returns are stored negative: flip both so overpayment (outstanding
	# past zero in the direction of settlement) still reads as PAID
	if grand_total < 0:
		outstanding, grand_total = -outstanding, -grand_total
	if outstanding <= 0:
		return "PAID"
	if outstanding < grand_total:
		return "PARTIAL"
	return "PENDING"


def _find_entity_by_irn(settings, irn):
	"""The IRN's second-to-last segment is the issuing entity's service id."""
	parts = cstr(irn).split("-")
	service_id = parts[-2] if len(parts) >= 3 else None
	for row in settings.billing_entities:
		if row.service_id == service_id:
			return row
	return None


@frappe.whitelist()
def lookup_irn(irn):
	"""Fetch the platform record for an IRN (reconciliation and debugging)."""
	frappe.only_for(("System Manager", "Accounts Manager"))
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	entity = _find_entity_by_irn(settings, irn)
	if not entity:
		frappe.throw(frappe._("No configured billing entity matches this IRN"))

	http, body = _platform_lookup(settings, entity, irn)
	return {"http": http, "body": body}


def _platform_lookup(settings, entity, irn):
	url = f"{cstr(settings.base_url).rstrip('/')}/api/v1/einvoice/lookup/{irn}"
	headers = {
		"x-client-id": entity.client_id,
		"x-client-secret": entity.get_password("client_secret"),
		"Content-Type": "application/json",
		"Accept": "application/json",
	}
	response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
	try:
		return response.status_code, response.json()
	except ValueError:
		return response.status_code, cstr(response.text)[:500]


# platform lookup reports transmit_status as a lowercase word
TRANSMIT_STATUS_LABELS = {
	"initiated": "INITIATED",
	"signed": "SIGNED",
	"transmitting": "TRANSMITTING",
	"transmitted": "TRANSMITTED",
}


def reconcile_transmissions():
	"""Daily scheduler job: true up non-terminal receipt statuses against the
	platform (webhooks are the primary sync; this is the safety net for
	missed deliveries) and retry transmissions that failed on connectivity."""
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	if not settings.enabled:
		return {"skipped": "disabled"}

	summary = {"checked": 0, "advanced": 0, "retried": 0, "payment_drift": 0, "missing_at_platform": 0}

	pending = frappe.get_all(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"nrs_irn": ["is", "set"],
			"nrs_receipt_status": ["in", ["INITIATED", "SIGNED", "TRANSMITTING"]],
		},
		pluck="name",
		limit=200,
	)
	for name in pending:
		summary["checked"] += 1
		try:
			_reconcile_one(name, settings, summary)
		except Exception:
			frappe.log_error(
				title=f"NRS reconciliation failed for {name}",
				message=frappe.get_traceback(),
			)

	failed = frappe.get_all(
		"Sales Invoice",
		filters={"docstatus": 1, "nrs_receipt_status": "FAILED"},
		pluck="name",
		limit=50,
	)
	for name in failed:
		try:
			transmit_invoice(frappe.get_doc("Sales Invoice", name), settings)
			summary["retried"] += 1
		except Exception:
			frappe.log_error(
				title=f"NRS reconciliation retry failed for {name}",
				message=frappe.get_traceback(),
			)

	_logger().info(f"reconciliation summary: {summary}")
	return summary


def _reconcile_one(name, settings, summary):
	irn, current = frappe.db.get_value(
		"Sales Invoice", name, ["nrs_irn", "nrs_receipt_status"]
	)
	entity = _find_entity_by_irn(settings, irn)
	if not entity:
		return

	http, body = _platform_lookup(settings, entity, irn)
	if not isinstance(body, dict):
		return
	if http != 200:
		if cint(body.get("code")) == 23:
			# known platform inconsistency: signed at NRS but absent from the
			# platform record store - surface for the platform team
			summary["missing_at_platform"] += 1
			frappe.log_error(
				title=f"NRS record missing for {name}",
				message=f"lookup {irn} returned code 23 (IRN record not found)",
			)
		return

	data = body.get("data") if isinstance(body.get("data"), dict) else {}
	label = TRANSMIT_STATUS_LABELS.get(cstr(data.get("transmit_status")).lower()) or RECEIPT_STATUS_LABELS.get(
		cint(data.get("receipt_status"))
	)
	if label and RECEIPT_STATUS_RANK.get(label, 0) > RECEIPT_STATUS_RANK.get(cstr(current), 0):
		frappe.db.set_value(
			"Sales Invoice",
			name,
			{"nrs_receipt_status": label, "nrs_error": ""},
			update_modified=False,
		)
		summary["advanced"] += 1

	platform_pay = cstr(data.get("payment_status")).upper()
	outstanding, grand_total = frappe.db.get_value(
		"Sales Invoice", name, ["outstanding_amount", "grand_total"]
	)
	local_pay = _derive_payment_status(outstanding, grand_total)
	if platform_pay and platform_pay != local_pay:
		summary["payment_drift"] += 1
		_logger().info(f"{name}: payment drift local={local_pay} platform={platform_pay}")


def _notify_problem(doc, status, error):
	"""Bell notification for accounts staff, created directly because the
	result fields are written with db_set (which does not fire the
	Notification doctype's Value Change triggers)."""
	users = frappe.get_all(
		"Has Role",
		filters={"role": "Accounts Manager", "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	if not users:
		return
	enabled = frappe.get_all(
		"User", filters={"enabled": 1, "name": ["in", users]}, pluck="name"
	)
	for user in enabled:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"type": "Alert",
				"document_type": doc.doctype,
				"document_name": doc.name,
				"for_user": user,
				"subject": f"NRS {status}: {doc.name}",
				"email_content": cstr(error),
			}
		).insert(ignore_permissions=True)


@frappe.whitelist()
def test_connection():
	"""Validate each billing entity's credentials against the platform.

	Probe via lookup with a nonexistent IRN: code 23 / HTTP 404 proves the
	credentials authenticated (record simply missing); code 11 / 401 / 403
	means they did not.
	"""
	frappe.only_for(("System Manager", "Accounts Manager"))
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	results = []
	for row in settings.billing_entities:
		probe = f"CONNECTIONTEST-{row.service_id}-19700101"
		try:
			http, body = _platform_lookup(settings, row, probe)
		except requests.exceptions.RequestException:
			results.append(
				{"company": row.company, "ok": False, "detail": "Platform unreachable - check Base URL / network"}
			)
			continue
		code = cint(body.get("code")) if isinstance(body, dict) else None
		if code == 11 or http in (401, 403):
			results.append(
				{"company": row.company, "ok": False, "detail": "Invalid credentials - check Client ID and Client Secret"}
			)
		elif code == 23 or http in (200, 404):
			results.append({"company": row.company, "ok": True, "detail": "Credentials OK"})
		else:
			results.append(
				{"company": row.company, "ok": False, "detail": f"Unexpected response (HTTP {http})"}
			)
	return results
