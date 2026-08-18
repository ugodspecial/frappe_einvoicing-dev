# Copyright (c) 2026, Doftwerks West Africa Limited and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class NRSEInvoiceSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from doftwerks_nrs.doftwerks_nrs_e_invoicing.doctype.nrs_billing_entity.nrs_billing_entity import (
			NRSBillingEntity,
		)
		from frappe.types import DF

		auto_transmit_on_submit: DF.Check
		base_url: DF.Data | None
		billing_entities: DF.Table[NRSBillingEntity]
		enabled: DF.Check
		provider: DF.Link

	# end: auto-generated types

	pass
