# Copyright (c) 2026, Doftwerks West Africa Limited and contributors
# For license information, please see license.txt

"""Doftwerks Access Point Provider implementation.

Handles transmission, webhook processing, and status polling via the Doftwerks
NRS Access Point API. This is the original implementation extracted from einvoice.py
into the provider interface.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import frappe
import requests
from frappe.utils import cint, cstr

from .base import EInvoiceProvider


class DoftwerksProvider(EInvoiceProvider):
	"""Doftwerks NRS Access Point Provider.

	Implements the provider interface for the Doftwerks platform.
	Doftwerks is an NRS-accredited system integrator and access point provider
	based in West Africa.
	"""

	PROVIDER_NAME = "doftwerks"

	# Doftwerks-specific error patterns (regex needles matched top to bottom)
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
		(
			"mismatch",
			"NRS reports a TAX ID mismatch: the Supplier TIN configured for this "
			"Company does not match the TIN registered to these NRS credentials. "
			"Check the billing entity row in NRS E-Invoice Settings.",
		),
		(
			"tax id",
			"NRS reports a TAX ID mismatch: the Supplier TIN configured for this "
			"Company does not match the TIN registered to these NRS credentials. "
			"Check the billing entity row in NRS E-Invoice Settings.",
		),
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
		(
			"hsn",
			"NRS rejected an item's classification. Goods need an HSN code in "
			"0000.00 format, services an ISIC code. "
			"Check the NRS fields on the invoice's Item(s) and retry.",
		),
		(
			"isic",
			"NRS rejected an item's classification. Goods need an HSN code in "
			"0000.00 format, services an ISIC code. "
			"Check the NRS fields on the invoice's Item(s) and retry.",
		),
		(
			"category",
			"NRS rejected an item's classification. Goods need an HSN code in "
			"0000.00 format, services an ISIC code. "
			"Check the NRS fields on the invoice's Item(s) and retry.",
		),
		(
			"not found",
			"NRS has no record of this IRN yet. The invoice may not have been "
			"transmitted, or the platform's record is delayed - check the "
			"transmission status and retry later.",
		),
		(
			"timed out",
			"The NRS e-invoicing platform could not be reached. "
			"The invoice was NOT transmitted - retry once the platform is back online.",
		),
		(
			"timeout",
			"The NRS e-invoicing platform could not be reached. "
			"The invoice was NOT transmitted - retry once the platform is back online.",
		),
		(
			"connection",
			"The NRS e-invoicing platform could not be reached. "
			"The invoice was NOT transmitted - retry once the platform is back online.",
		),
		(
			"unavailable",
			"The NRS e-invoicing platform could not be reached. "
			"The invoice was NOT transmitted - retry once the platform is back online.",
		),
		(
			"offline",
			"The NRS e-invoicing platform could not be reached. "
			"The invoice was NOT transmitted - retry once the platform is back online.",
		),
		(
			"busy",
			"The NRS e-invoicing platform could not be reached. "
			"The invoice was NOT transmitted - retry once the platform is back online.",
		),
	]

	def validate_credentials(self, credentials: Dict[str, Any]) -> Tuple[bool, str]:
		"""Test Doftwerks connection with the given credentials.

		Args:
			credentials: Dict with 'base_url', 'client_id', 'client_secret'

		Returns:
			Tuple of (success, message)
		"""
		base_url = credentials.get("base_url", "").strip()
		client_id = credentials.get("client_id", "").strip()
		client_secret = credentials.get("client_secret", "").strip()

		if not base_url or not client_id or not client_secret:
			return False, "Missing base_url, client_id, or client_secret"

		url = f"{base_url.rstrip('/')}/api/v1/test"
		headers = {
			"x-client-id": client_id,
			"x-client-secret": client_secret,
			"Content-Type": "application/json",
			"Accept": "application/json",
		}

		try:
			response = requests.post(url, headers=headers, timeout=self.REQUEST_TIMEOUT)
			if response.ok:
				try:
					body = response.json()
					message = body.get("message", "Connection successful")
					return True, message
				except ValueError:
					return True, "Connection successful"
			else:
				try:
					body = response.json()
					message = body.get("message", f"HTTP {response.status_code}")
				except ValueError:
					message = f"HTTP {response.status_code}"
				return False, message
		except requests.exceptions.RequestException as e:
			return False, f"Connection failed: {str(e)}"

	def transmit(self, payload: Dict[str, Any], credentials: Dict[str, Any]) -> Dict[str, Any]:
		"""Transmit invoice to NRS via Doftwerks.

		Args:
			payload: NRS-standard invoice payload
			credentials: Dict with 'base_url', 'client_id', 'client_secret'

		Returns:
			Standard result dict
		"""
		base_url = credentials.get("base_url", "").strip()
		client_id = credentials.get("client_id", "").strip()
		client_secret = credentials.get("client_secret", "").strip()

		if not base_url or not client_id or not client_secret:
			return {
				"success": False,
				"irn": "",
				"status": "",
				"qr_code": None,
				"error": "Missing Doftwerks credentials (base_url, client_id, client_secret)",
			}

		url = f"{base_url.rstrip('/')}/api/v1/einvoice/transmit"
		headers = {
			"x-client-id": client_id,
			"x-client-secret": client_secret,
			"Content-Type": "application/json",
			"Accept": "application/json",
		}

		try:
			response = requests.post(url, json=payload, headers=headers, timeout=self.REQUEST_TIMEOUT)
		except requests.exceptions.RequestException as e:
			error_msg = self.get_friendly_error(str(e))
			frappe.logger("nrs_doftwerks").error(f"Request failed: {str(e)}")
			return {
				"success": False,
				"irn": "",
				"status": "",
				"qr_code": None,
				"error": error_msg,
			}

		return self.parse_response(response, payload)

	def parse_response(self, response: Any, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
		"""Parse Doftwerks response into standard format.

		Args:
			response: requests.Response object
			payload: Optional original payload (used for fallback IRN)

		Returns:
			Standard result dict
		"""
		try:
			body = response.json()
		except ValueError:
			body = {}

		message = cstr(body.get("message", ""))
		data = body.get("data")
		if not isinstance(data, dict):
			data = {}

		# Doftwerks returns success in multiple ways
		signed_in_message = "signed" in message.lower()
		success = bool(data.get("irn") or data.get("receipt_status")) or signed_in_message

		if not success and response.status_code < 400:
			# Treat non-error HTTP codes without IRN as failure
			success = False

		if not success:
			raw_error = message or cstr(response.text)[:500] or f"HTTP {response.status_code}"
			error_msg = self.get_friendly_error(raw_error)
			frappe.logger("nrs_doftwerks").warning(
				f"Transmission failed: HTTP {response.status_code}\n{cstr(response.text)[:5000]}"
			)
			return {
				"success": False,
				"irn": "",
				"status": "",
				"qr_code": None,
				"error": error_msg,
				"raw_response": body,
			}

		# Extract receipt status label
		status_code = cint(data.get("receipt_status"))
		status_labels = {
			1: "INITIATED",
			2: "SIGNED",
			3: "TRANSMITTING",
			4: "TRANSMITTED",
		}
		status_label = status_labels.get(status_code, "SIGNED" if signed_in_message else "TRANSMITTED")

		# Use provided IRN or fall back to payload IRN
		irn = data.get("irn")
		if not irn and payload:
			irn = payload.get("irn")

		qr_code = data.get("qr_code")

		frappe.logger("nrs_doftwerks").info(
			f"Transmission successful: irn={irn}, status={status_label}"
		)

		return {
			"success": True,
			"irn": irn or "",
			"status": status_label,
			"qr_code": qr_code,
			"error": "",
			"raw_response": body,
		}

	def get_credential_fields(self) -> List[Dict[str, Any]]:
		"""Return schema for Doftwerks credential fields.

		Returns:
			List of field schemas for the settings form
		"""
		return [
			{
				"fieldname": "base_url",
				"label": "API Base URL",
				"fieldtype": "Data",
				"required": 1,
				"default": "https://api.doftwerks.com",
				"description": "Doftwerks API endpoint (contact support for custom URLs)",
			},
			{
				"fieldname": "client_id",
				"label": "Client ID",
				"fieldtype": "Data",
				"required": 1,
				"description": "Your Doftwerks-assigned Client ID",
			},
			{
				"fieldname": "client_secret",
				"label": "Client Secret",
				"fieldtype": "Password",
				"required": 1,
				"description": "Your Doftwerks-assigned Client Secret (will be encrypted)",
			},
			{
				"fieldname": "service_id",
				"label": "Service ID",
				"fieldtype": "Data",
				"required": 1,
				"description": "Your Doftwerks-assigned Service ID (used in IRN generation)",
			},
		]

	def handle_webhook(self, payload: Dict[str, Any], signature: Optional[str] = None) -> Dict[str, Any]:
		"""Process webhook from Doftwerks.

		Doftwerks sends status update events via POST webhook.
		Event type is checked to filter relevant events.

		Args:
			payload: Webhook JSON payload
			signature: Optional signature header (not currently verified by Doftwerks)

		Returns:
			Webhook data dict
		"""
		# Filter non-status events
		event_type = cstr(payload.get("eventType", "")).strip()
		if event_type and event_type != "TransmissionStatusEvent":
			return {
				"valid": True,
				"invoice_number": "",
				"irn": "",
				"status": "",
				"error": f"Ignoring event type: {event_type}",
			}

		# Extract data (may be nested or flat)
		data = payload.get("data") if isinstance(payload.get("data"), dict) else payload

		irn = cstr(data.get("irn", "")).strip()
		if not irn:
			return {
				"valid": False,
				"invoice_number": "",
				"irn": "",
				"status": "",
				"error": "No IRN in webhook payload",
			}

		# Extract status
		status_code = cint(data.get("receipt_status"))
		status_labels = {
			1: "INITIATED",
			2: "SIGNED",
			3: "TRANSMITTING",
			4: "TRANSMITTED",
		}
		status = status_labels.get(status_code, "")

		# Look up invoice by IRN
		invoice_name = frappe.db.get_value("Sales Invoice", {"nrs_irn": irn}, "name")

		frappe.logger("nrs_doftwerks").info(
			f"Webhook received: irn={irn}, status={status}, invoice={invoice_name}"
		)

		return {
			"valid": True,
			"invoice_number": invoice_name or "",
			"irn": irn,
			"status": status,
			"error": None,
		}

	def query_status(self, irn: str, credentials: Dict[str, Any]) -> Dict[str, Any]:
		"""Query Doftwerks for current invoice status.

		Used for status reconciliation and debugging.

		Args:
			irn: Invoice Reference Number
			credentials: Dict with 'base_url', 'client_id', 'client_secret'

		Returns:
			Status dict
		"""
		base_url = credentials.get("base_url", "").strip()
		client_id = credentials.get("client_id", "").strip()
		client_secret = credentials.get("client_secret", "").strip()

		if not base_url or not client_id or not client_secret:
			return {
				"success": False,
				"status": "",
				"error": "Missing Doftwerks credentials",
			}

		url = f"{base_url.rstrip('/')}/api/v1/einvoice/lookup/{irn}"
		headers = {
			"x-client-id": client_id,
			"x-client-secret": client_secret,
			"Content-Type": "application/json",
			"Accept": "application/json",
		}

		try:
			response = requests.get(url, headers=headers, timeout=self.REQUEST_TIMEOUT)
		except requests.exceptions.RequestException as e:
			frappe.logger("nrs_doftwerks").error(f"Status query failed: {str(e)}")
			return {
				"success": False,
				"status": "",
				"error": f"Connection failed: {str(e)}",
			}

		try:
			body = response.json()
		except ValueError:
			body = {}

		if not response.ok:
			error_msg = body.get("message", f"HTTP {response.status_code}")
			frappe.logger("nrs_doftwerks").warning(f"Status query failed: {error_msg}")
			return {
				"success": False,
				"status": "",
				"error": error_msg,
			}

		data = body.get("data") if isinstance(body.get("data"), dict) else {}

		# Doftwerks returns transmit_status as lowercase
		status_map = {
			"initiated": "INITIATED",
			"signed": "SIGNED",
			"transmitting": "TRANSMITTING",
			"transmitted": "TRANSMITTED",
		}
		raw_status = cstr(data.get("transmit_status", "")).lower()
		status = status_map.get(raw_status, raw_status.upper() if raw_status else "")

		frappe.logger("nrs_doftwerks").info(f"Status query successful: irn={irn}, status={status}")

		return {
			"success": True,
			"status": status,
			"error": None,
		}

	def get_friendly_error(self, raw_error: str) -> str:
		"""Convert Doftwerks error to user-friendly message.

		Matches error patterns against known Doftwerks errors and returns
		actionable guidance. Falls back to raw error if no pattern matches.

		Args:
			raw_error: Raw error message from API or exception

		Returns:
			User-friendly error message
		"""
		low = cstr(raw_error).lower()
		for needle, friendly in self.FRIENDLY_ERRORS:
			if re.search(needle, low):
				return friendly
		return cstr(raw_error)
