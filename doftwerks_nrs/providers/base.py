# Copyright (c) 2026, Doftwerks West Africa Limited and contributors
# For license information, please see license.txt

"""Abstract base class for NRS Access Point Providers.

All access point providers must inherit from EInvoiceProvider and implement
all abstract methods. This ensures a consistent interface for transmission,
credential management, webhook handling, and status polling regardless of
which provider is used.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any, List


class EInvoiceProvider(ABC):
	"""Abstract base for NRS Access Point Providers.

	Defines the interface that all e-invoice providers must implement.
	Providers handle:
	- Authentication and credential validation
	- Invoice transmission to their specific APIs
	- Response parsing and standardization
	- Error message formatting
	- Webhook verification and processing
	- Status polling/querying

	The NRS invoice payload structure (defined in einvoice.py) is universal
	and provider-agnostic. Providers only handle transmission mechanics.
	"""

	PROVIDER_NAME: Optional[str] = None
	"""Unique identifier for this provider (e.g., 'doftwerks', 'remita')."""

	REQUEST_TIMEOUT = 30
	"""Default timeout in seconds for API requests."""

	@abstractmethod
	def validate_credentials(self, credentials: Dict[str, Any]) -> Tuple[bool, str]:
		"""Test provider connection with given credentials.

		Args:
			credentials: Provider-specific credential dict (e.g., client_id, api_key).
					May contain encrypted values; provider responsible for decryption.

		Returns:
			Tuple of (success: bool, message: str)
			success: True if credentials are valid and provider is reachable
			message: Human-readable result (e.g., "Connected successfully" or "Invalid API key")
		"""
		pass

	@abstractmethod
	def transmit(self, payload: Dict[str, Any], credentials: Dict[str, Any]) -> Dict[str, Any]:
		"""Transmit NRS invoice payload via this provider's API.

		Args:
			payload: NRS-compliant invoice payload (standardized across all providers).
					Contains invoice_number, line items, customer, supplier, taxes, etc.
			credentials: Provider-specific credentials (e.g., client_id, api_key).

		Returns:
			Standard result dict:
			{
				'success': bool,           # True if transmitted successfully
				'irn': str,                # Invoice Reference Number (empty if failed)
				'status': str,             # Receipt status label (e.g., 'TRANSMITTED', 'SIGNED')
				'qr_code': str or None,    # Base64-encoded QR code image (if available)
				'error': str,              # Human-readable error message (if failed)
				'raw_response': dict,      # Optional: full provider response for debugging
			}

		Raises:
			No exceptions should be raised. All errors caught and returned in result['error'].
		"""
		pass

	@abstractmethod
	def parse_response(self, response: Any, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
		"""Parse provider-specific API response into standard format.

		This is called by transmit() to normalize the provider's response.
		Extracts IRN, receipt status, QR code, and any error messages.

		Args:
			response: Provider's HTTP response object (requests.Response or similar).
			payload: Original NRS payload (used for fallback values like IRN).

		Returns:
			Standard result dict (same structure as transmit()).
		"""
		pass

	@abstractmethod
	def get_credential_fields(self) -> List[Dict[str, Any]]:
		"""Return schema for provider-specific credential input fields.

		Used by the settings form UI to dynamically generate credential input fields.
		Each field should specify fieldname, label, fieldtype, required, default, etc.

		Returns:
			List of field schema dicts:
			[
				{
					'fieldname': 'client_id',
					'label': 'Client ID',
					'fieldtype': 'Data',
					'required': 1,
					'description': 'Your provider-assigned client ID'
				},
				{
					'fieldname': 'client_secret',
					'label': 'Client Secret',
					'fieldtype': 'Password',
					'required': 1,
					'encrypted': 1
				},
				...
			]
		"""
		pass

	@abstractmethod
	def handle_webhook(self, payload: Dict[str, Any], signature: Optional[str] = None) -> Dict[str, Any]:
		"""Verify and process webhook callback from provider.

		Provider may send real-time invoice status updates via webhook.
		This method verifies the webhook signature (if provided) and extracts
		the invoice reference and new status.

		Args:
			payload: Webhook payload from provider (JSON-decoded).
			signature: Optional signature header for verification.

		Returns:
			Dict with webhook data:
			{
				'valid': bool,             # True if signature valid or no signature required
				'invoice_number': str,     # ERPNext invoice name (to identify which doc to update)
				'irn': str,                # Invoice Reference Number from provider
				'status': str,             # New receipt status
				'error': str or None,      # Error message if webhook invalid
			}
		"""
		pass

	@abstractmethod
	def query_status(self, irn: str, credentials: Dict[str, Any]) -> Dict[str, Any]:
		"""Poll provider for current status of a transmitted invoice.

		Used for status reconciliation (daily sweep) and manual status checks.

		Args:
			irn: Invoice Reference Number (returned by transmit()).
			credentials: Provider-specific credentials for this query.

		Returns:
			Status dict:
			{
				'success': bool,           # True if query succeeded
				'status': str,             # Current receipt status (e.g., 'TRANSMITTED')
				'error': str or None,      # Error message if query failed
			}
		"""
		pass

	def get_friendly_error(self, raw_error: str) -> str:
		"""Convert provider error message to user-friendly guidance.

		Override in subclasses to handle provider-specific error patterns.
		Default implementation returns the raw error.

		Args:
			raw_error: Raw error message from provider API or exception.

		Returns:
			User-friendly error message with actionable guidance.
		"""
		return raw_error

	def on_before_transmit(self, doc: Any, payload: Dict[str, Any]) -> None:
		"""Hook called before transmission (optional).

		Providers can override to modify payload or perform pre-transmission setup.
		Called by core code just before calling transmit().

		Args:
			doc: The Sales Invoice document being transmitted.
			payload: The NRS payload about to be sent (can be modified).
		"""
		pass

	def on_after_transmit(self, doc: Any, result: Dict[str, Any]) -> None:
		"""Hook called after transmission (optional).

		Providers can override to perform post-transmission actions
		(e.g., store provider-specific metadata on the invoice).

		Args:
			doc: The Sales Invoice document that was transmitted.
			result: The result dict returned from transmit().
		"""
		pass

	def update_payment_status(self, irn: str, payment_status: str, credentials: Dict[str, Any]) -> Dict[str, Any]:
		"""Update payment status on provider platform (optional).

		Some providers may support updating payment status separately from
		invoice transmission. Override in subclasses if supported.

		Args:
			irn: Invoice Reference Number
			payment_status: One of "PAID", "PARTIAL", "PENDING"
			credentials: Provider-specific credentials

		Returns:
			Result dict:
			{
				'success': bool,
				'error': str or None,
			}
		"""
		return {
			"success": False,
			"error": "Payment status update not supported by this provider",
		}
