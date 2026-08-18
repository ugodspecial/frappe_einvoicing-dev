# Copyright (c) 2026, Doftwerks West Africa Limited and contributors
# For license information, please see license.txt

"""
Post-model sync patch to migrate existing Doftwerks settings to multi-provider model.

This patch:
1. Creates the E-Invoice Provider record for Doftwerks
2. Updates NRS E-Invoice Settings with provider = "doftwerks"
3. Migrates each billing entity to use provider_credentials_json
"""

import frappe
import json


def execute():
	"""Migrate existing Doftwerks settings to provider model."""
	
	# 1. Create E-Invoice Provider record for Doftwerks
	create_doftwerks_provider()
	
	# 2. Update NRS E-Invoice Settings
	update_settings()
	
	# 3. Migrate billing entities
	migrate_billing_entities()
	
	frappe.db.commit()
	print("Multi-provider migration completed successfully")


def create_doftwerks_provider():
	"""Create the Doftwerks provider record if it doesn't exist."""
	if not frappe.db.exists("E-Invoice Provider", "doftwerks"):
		provider = frappe.get_doc({
			"doctype": "E-Invoice Provider",
			"title": "Doftwerks Access Point",
			"module": "doftwerks_nrs",
			"class_path": "doftwerks_nrs.providers.doftwerks.DoftwerksProvider",
			"is_active": 1,
			"credential_schema": {
				"fields": [
					{
						"fieldname": "base_url",
						"label": "API Base URL",
						"fieldtype": "Data",
						"required": 1,
						"default": "https://api.doftwerks.com",
						"description": "Doftwerks API endpoint (contact support for custom URLs)"
					},
					{
						"fieldname": "client_id",
						"label": "Client ID",
						"fieldtype": "Data",
						"required": 1,
						"description": "Your Doftwerks-assigned Client ID"
					},
					{
						"fieldname": "client_secret",
						"label": "Client Secret",
						"fieldtype": "Password",
						"required": 1,
						"description": "Your Doftwerks-assigned Client Secret (will be encrypted)"
					},
					{
						"fieldname": "service_id",
						"label": "Service ID",
						"fieldtype": "Data",
						"required": 1,
						"description": "Your Doftwerks-assigned Service ID (used in IRN generation)"
					}
				]
			}
		})
		provider.insert(ignore_permissions=True)
		print("Created E-Invoice Provider: doftwerks")
	else:
		print("E-Invoice Provider 'doftwerks' already exists")


def update_settings():
	"""Update NRS E-Invoice Settings with provider field."""
	settings = frappe.get_single("NRS E-Invoice Settings")
	
	if not settings.provider:
		settings.provider = "doftwerks"
		settings.save(ignore_permissions=True)
		print("Updated NRS E-Invoice Settings: provider = 'doftwerks'")
	else:
		print("NRS E-Invoice Settings already has provider set")


def migrate_billing_entities():
	"""Migrate each billing entity to use provider_credentials_json."""
	settings = frappe.get_single("NRS E-Invoice Settings")
	
	for entity in settings.billing_entities:
		# Skip if already migrated
		if entity.provider_credentials_json:
			print(f"Billing entity {entity.company} already migrated, skipping")
			continue
		
		# Set provider if not set
		if not entity.provider:
			entity.provider = "doftwerks"
		
		# Build credentials JSON from legacy fields
		credentials = {}
		
		# Use settings.base_url as default, but allow override if entity has it
		base_url = entity.get("base_url") or settings.base_url or "https://api.doftwerks.com"
		credentials["base_url"] = base_url
		
		if entity.client_id:
			credentials["client_id"] = entity.client_id
		if entity.client_secret:
			# client_secret is a password field, get decrypted value
			credentials["client_secret"] = entity.get_password("client_secret")
		if entity.business_id:
			credentials["business_id"] = entity.business_id
		if entity.service_id:
			credentials["service_id"] = entity.service_id
		
		# Save credentials as JSON
		entity.provider_credentials_json = json.dumps(credentials)
		
		# Note: We keep legacy fields for rollback/backward compatibility
		# They can be cleared in a future cleanup patch
		
		print(f"Migrated billing entity: {entity.company} -> provider_credentials_json")
	
	settings.save(ignore_permissions=True)
	print(f"Migrated {len(settings.billing_entities)} billing entities")


def rollback():
	"""Rollback migration (for testing)."""
	# Delete the provider record
	if frappe.db.exists("E-Invoice Provider", "doftwerks"):
		frappe.delete_doc("E-Invoice Provider", "doftwerks", ignore_permissions=True)
	
	# Reset settings
	settings = frappe.get_single("NRS E-Invoice Settings")
	settings.provider = ""
	settings.save(ignore_permissions=True)
	
	# Clear provider fields on billing entities
	for entity in settings.billing_entities:
		entity.provider = ""
		entity.provider_credentials_json = ""
	settings.save(ignore_permissions=True)
	
	frappe.db.commit()
	print("Migration rolled back")