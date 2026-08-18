# Copyright (c) 2026, YoungAndCode LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EInvoiceProvider(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		class_path: DF.Data
		credential_schema: DF.JSON | None
		is_active: DF.Check
		module: DF.Data
		title: DF.Data
	# end: auto-generated types

	def validate(self):
		"""Validate the provider configuration."""
		self._validate_class_path()
		self._sync_credential_schema()

	def _validate_class_path(self):
		"""Verify the provider class can be imported."""
		if not self.class_path:
			return
		try:
			module_path, class_name = self.class_path.rsplit(".", 1)
			__import__(module_path)
		except (ImportError, ValueError) as e:
			frappe.throw(f"Invalid class path '{self.class_path}': {str(e)}")

	def _sync_credential_schema(self):
		"""Sync credential schema from the provider class if available."""
		if not self.class_path or not self.is_active:
			return
		try:
			module_path, class_name = self.class_path.rsplit(".", 1)
			module = __import__(module_path, fromlist=[class_name])
			provider_class = getattr(module, class_name)
			if hasattr(provider_class, "get_credential_fields"):
				# Instantiate without settings to get schema
				provider = provider_class()
				self.credential_schema = {"fields": provider.get_credential_fields()}
		except Exception:
			# Don't fail validation if schema sync fails
			pass

	@frappe.whitelist()
	def test_connection(self, credentials: dict = None):
		"""Test connection using this provider."""
		if not self.class_path:
			frappe.throw("Provider class path not configured")
		
		module_path, class_name = self.class_path.rsplit(".", 1)
		module = __import__(module_path, fromlist=[class_name])
		provider_class = getattr(module, class_name)
		provider = provider_class()
		
		if not credentials:
			credentials = {}
		
		success, message = provider.validate_credentials(credentials)
		return {"success": success, "message": message}