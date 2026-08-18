# Copyright (c) 2026, YoungAndCode LTD and contributors
# For license information, please see license.txt

import frappe
try:
	from frappe.tests import IntegrationTestCase as FrappeTestCase
except ImportError:
	from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

import doftwerks_nrs.einvoice as einvoice
from doftwerks_nrs.providers.doftwerks import DoftwerksProvider

einvoice_provider = DoftwerksProvider()

ENTITY = frappe._dict(
	company="Test Entity Co",
	client_id="test-client",
	business_id="test-business",
	service_id="AB12CD34",
	supplier_tin="00000000-0001",
	supplier_email="supplier@example.com",
	supplier_phone="+2340000000001",
	supplier_business_description="Testing",
	supplier_street="1 Test Street",
	supplier_city="Lagos",
	supplier_postal_zone="100001",
	supplier_lga="NG-LA-EOS",
	supplier_state="NG-LA",
	supplier_country="NG",
)


class FakeResponse:
	def __init__(self, status_code, body):
		self.status_code = status_code
		self._body = body
		self.text = frappe.as_json(body)
		self.ok = status_code < 400

	def json(self):
		return self._body


class MiniDoc:
	doctype = "Sales Invoice"
	name = "TEST-INV-0001"

	def __init__(self):
		self.written = {}

	def db_set(self, field, value, update_modified=True):
		self.written[field] = value

	def get(self, key):
		return self.written.get(key)


def get_or_make_item(code, is_service, tax_code, hsn):
	if not frappe.db.exists("Item", code):
		leaf = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": code,
				"item_name": code,
				"item_group": leaf,
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"nrs_is_service": is_service,
				"nrs_hsn_code": hsn,
				"nrs_product_category": "Test category",
				"nrs_tax_code": tax_code,
			}
		).insert(ignore_permissions=True)
	return code


def get_or_make_customer(name, complete):
	if not frappe.db.exists("Customer", name):
		doc = {
			"doctype": "Customer",
			"customer_name": name,
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
			"territory": "All Territories",
			"nrs_is_b2b": 1,
		}
		if complete:
			doc.update(
				{
					"nrs_tin": "12345678-0001",
					"nrs_state_code": "NG-LA",
					"nrs_lga_code": "NG-LA-IKD",
					"nrs_business_description": "Test business",
					"email_id": "customer@example.com",
					"mobile_no": "+2340000000002",
				}
			)
		frappe.get_doc(doc).insert(ignore_permissions=True)

	if complete and not frappe.db.exists("Address", name + "-Billing"):
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": name,
				"address_type": "Billing",
				"address_line1": "2 Test Avenue",
				"city": "Ikeja",
				"pincode": "100271",
				"country": "Nigeria",
				"is_primary_address": 1,
				"links": [{"link_doctype": "Customer", "link_name": name}],
			}
		).insert(ignore_permissions=True)
	return name


def make_invoice_doc(customer, rows, is_return=0):
	si = frappe.new_doc("Sales Invoice")
	si.name = "TESTSINV-0001"
	si.customer = customer
	si.customer_name = customer
	si.posting_date = getdate("2026-01-15")
	si.due_date = getdate("2026-02-15")
	si.currency = "NGN"
	si.status = "Unpaid"
	si.is_return = is_return
	net = 0
	for row in rows:
		si.append("items", row)
		net += row["net_amount"]
	si.net_total = net
	si.grand_total = net
	si.outstanding_amount = net
	return si


class TestDomainRules(FrappeTestCase):
	def test_invoice_type_codes_are_inverted_and_strings(self):
		# NRS codes are the reverse of UBL-1001 and must be strings —
		# see docs/CONTEXT.md §2.2 before "fixing" this
		self.assertEqual(einvoice.INVOICE_TYPE_CODES["Invoice"], "381")
		self.assertEqual(einvoice.INVOICE_TYPE_CODES["Credit Note"], "380")
		self.assertEqual(einvoice.INVOICE_TYPE_CODES["Debit Note"], "384")

	def test_receipt_status_labels(self):
		self.assertEqual(
			einvoice.RECEIPT_STATUS_LABELS,
			{1: "INITIATED", 2: "SIGNED", 3: "TRANSMITTING", 4: "TRANSMITTED"},
		)

	def test_derive_payment_status(self):
		cases = [
			(0, 1000, "PAID"),
			(-0.005, 1000, "PAID"),  # overpayment must still read PAID
			(400, 1000, "PARTIAL"),
			(1000, 1000, "PENDING"),
			(-1000, -1000, "PENDING"),  # unpaid credit note
			(-500, -1000, "PARTIAL"),
			(0, -1000, "PAID"),
		]
		for outstanding, total, want in cases:
			self.assertEqual(einvoice._derive_payment_status(outstanding, total), want)

	def test_find_entity_by_irn(self):
		settings = frappe._dict(billing_entities=[ENTITY])
		self.assertEqual(
			einvoice._find_entity_by_irn(settings, "INV1-AB12CD34-20260101"), ENTITY
		)
		self.assertIsNone(einvoice._find_entity_by_irn(settings, "INV1-OTHER-20260101"))
		self.assertIsNone(einvoice._find_entity_by_irn(settings, "garbage"))

	def test_set_receipt_type(self):
		doc = frappe._dict(is_return=1, is_debit_note=0, nrs_receipt_type=None)
		einvoice.set_receipt_type(doc)
		self.assertEqual(doc.nrs_receipt_type, "Credit Note")

		doc = frappe._dict(is_return=0, is_debit_note=1, nrs_receipt_type="Invoice")
		einvoice.set_receipt_type(doc)
		self.assertEqual(doc.nrs_receipt_type, "Debit Note")

		doc = frappe._dict(is_return=0, is_debit_note=0, nrs_receipt_type=None)
		einvoice.set_receipt_type(doc)
		self.assertEqual(doc.nrs_receipt_type, "Invoice")

	def test_doc_amount_absolute_only_for_returns(self):
		self.assertEqual(einvoice._doc_amount(frappe._dict(is_return=1), -1075.5), 1075.5)
		self.assertEqual(einvoice._doc_amount(frappe._dict(is_return=0), -1075.5), -1075.5)


class TestFriendlyErrors(FrappeTestCase):
	def test_specific_before_general(self):
		# supplier credential mismatch must outrank the generic customer-TIN match
		self.assertEqual(
			einvoice_provider.get_friendly_error("TAX ID mismatch: supplier tin wrong"),
			DoftwerksProvider.FRIENDLY_ERRORS[2][1],  # "mismatch" message
		)

	def test_tin_is_word_bounded(self):
		# "Accounting" contains the substring "tin" — must NOT match
		got = einvoice_provider.get_friendly_error("Accounting parties APP might be busy")
		self.assertEqual(got, einvoice.OFFLINE_MESSAGE)

	def test_customer_tin_still_matches(self):
		got = einvoice_provider.get_friendly_error("accountingcustomerparty.tin is required")
		self.assertIn("Customer", got)
		self.assertIn("TIN", got)

	def test_classification_and_unknown(self):
		self.assertEqual(
			einvoice_provider.get_friendly_error("hsn_code is invalid"),
			DoftwerksProvider.FRIENDLY_ERRORS[10][1],  # "hsn" message
		)
		self.assertEqual(einvoice_provider.get_friendly_error("never seen before"), "never seen before")


class TestParseResponse(FrappeTestCase):
	def test_signed_but_offline_is_success(self):
		response = FakeResponse(
			200,
			{
				"code": 55,
				"status": "success",
				"message": "Invoice is Signed but could not transmit. "
				"Accounting parties APP might be offline or busy",
				"data": [],
			},
		)
		result = einvoice_provider.parse_response(response, {"irn": "X-AB12CD34-20260101"})
		self.assertTrue(result["success"])
		self.assertEqual(result["irn"], "X-AB12CD34-20260101")
		self.assertEqual(result["status"], "SIGNED")
		self.assertEqual(result["error"], "")

	def test_full_success_maps_status(self):
		response = FakeResponse(
			200,
			{"code": 0, "status": "success", "message": "ok", "data": {"irn": "REAL-IRN", "receipt_status": 4}},
		)
		result = einvoice_provider.parse_response(response, {"irn": "LOCAL-IRN"})
		self.assertTrue(result["success"])
		self.assertEqual(result["irn"], "REAL-IRN")
		self.assertEqual(result["status"], "TRANSMITTED")

	def test_rejection_writes_friendly_error(self):
		response = FakeResponse(
			422,
			{"code": 40, "status": "error", "message": "hsn_code is invalid", "data": []},
		)
		result = einvoice_provider.parse_response(response, {"irn": "LOCAL-IRN"})
		self.assertFalse(result["success"])
		self.assertEqual(result["error"], DoftwerksProvider.FRIENDLY_ERRORS[10][1])  # "hsn" message
		self.assertEqual(result["irn"], "")


class TestBuildPayload(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.goods = get_or_make_item("_Test NRS Goods", 0, "STANDARD_VAT", "1234.56")
		cls.service = get_or_make_item("_Test NRS Service", 1, "ZERO_VAT", "6311")
		cls.customer = get_or_make_customer("_Test NRS Customer", complete=True)
		cls.bare_customer = get_or_make_customer("_Test NRS Customer Bare", complete=False)

	def rows(self):
		return [
			{"item_code": self.goods, "item_name": "Goods", "qty": 2, "rate": 100, "net_amount": 200},
			{"item_code": self.service, "item_name": "Service", "qty": 1, "rate": 50, "net_amount": 50},
		]

	def test_payload_shape(self):
		errors = []
		doc = make_invoice_doc(self.customer, self.rows())
		payload = einvoice.build_payload(doc, ENTITY, errors)

		self.assertEqual(errors, [])
		self.assertEqual(payload["irn"], "TESTSINV0001-AB12CD34-20260115")
		self.assertEqual(payload["invoice_type_code"], "381")
		self.assertEqual(payload["payment_status"], "PENDING")
		self.assertEqual(payload["invoice_kind"], "B2B")
		self.assertEqual(payload["billing_reference"], [])
		self.assertEqual(payload["accounting_customer_party"]["telephone"], "+2340000000002")

		goods_line, service_line = payload["invoice_line"]
		# nested item/price with flat classification; unused pair is "" not None
		self.assertEqual(goods_line["item"]["name"], "Goods")
		self.assertEqual(goods_line["price"]["price_amount"], 100)
		self.assertEqual(goods_line["price"]["price_unit"], "NGN per 1")
		self.assertEqual(goods_line["hsn_code"], "1234.56")
		self.assertEqual(goods_line["isic_code"], "")
		self.assertEqual(service_line["isic_code"], "6311")
		self.assertEqual(service_line["hsn_code"], "")
		self.assertEqual(goods_line["tax_category"], [{"id": "STANDARD_VAT", "percent": 7.5}])
		self.assertEqual(service_line["tax_category"], [{"id": "ZERO_VAT", "percent": 0.0}])

		subtotals = payload["tax_total"][0]["tax_subtotal"]
		self.assertEqual(len(subtotals), 2)
		standard = next(s for s in subtotals if s["tax_category"]["id"] == "STANDARD_VAT")
		self.assertEqual(standard["taxable_amount"], 200)
		self.assertEqual(standard["tax_amount"], 15.0)

	def test_preflight_collects_all_problems(self):
		errors = []
		doc = make_invoice_doc(self.bare_customer, self.rows())
		einvoice.build_payload(doc, ENTITY, errors)
		joined = "\n".join(errors)
		for needle in ("street", "city", "TIN", "State Code", "LGA Code", "email"):
			self.assertIn(needle, joined)

	def test_credit_note_absolute_amounts_and_billing_reference(self):
		errors = []
		rows = [
			{"item_code": self.goods, "item_name": "Goods", "qty": -2, "rate": 100, "net_amount": -200}
		]
		doc = make_invoice_doc(self.customer, rows, is_return=1)
		doc.nrs_receipt_type = "Credit Note"
		payload = einvoice.build_payload(doc, ENTITY, errors)

		self.assertEqual(payload["invoice_type_code"], "380")
		line = payload["invoice_line"][0]
		self.assertEqual(line["invoiced_quantity"], 2)
		self.assertEqual(line["line_extension_amount"], 200)
		self.assertEqual(payload["legal_monetary_total"]["payable_amount"], 200)
		# no return_against -> pre-flight error, not a payload crash
		self.assertTrue(any("original invoice" in e for e in errors))


class MockProvider(DoftwerksProvider):
	PROVIDER_NAME = "mock"
	def transmit(self, payload, credentials):
		return {"success": True, "irn": "MOCK-IRN", "status": "TRANSMITTED", "error": ""}

class TestMultiProvider(FrappeTestCase):
	def test_provider_selection(self):
		settings = frappe.get_doc("NRS E-Invoice Settings")
		entity = frappe._dict(provider="mock", company="Test Co")
		
		# Register mock provider
		from doftwerks_nrs.providers import register_provider
		register_provider(MockProvider)
		
		provider = einvoice._get_provider_for_entity(entity, settings)
		self.assertEqual(provider.PROVIDER_NAME, "mock")
