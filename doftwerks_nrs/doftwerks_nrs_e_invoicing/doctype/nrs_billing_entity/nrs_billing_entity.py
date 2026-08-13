# Copyright (c) 2026, Doftwerks West Africa Limited and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class NRSBillingEntity(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		business_id: DF.Data
		client_id: DF.Data
		client_secret: DF.Password
		company: DF.Link
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		service_id: DF.Data
		supplier_business_description: DF.Data | None
		supplier_city: DF.Data | None
		supplier_country: DF.Data | None
		supplier_email: DF.Data | None
		supplier_lga: DF.Data | None
		supplier_phone: DF.Data | None
		supplier_postal_zone: DF.Data | None
		supplier_state: DF.Data | None
		supplier_street: DF.Data | None
		supplier_tin: DF.Data

	# end: auto-generated types

	pass
