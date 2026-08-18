# Copyright (c) 2026, YoungAndCode LTD and contributors
# For license information, please see license.txt

"""Provider registry and discovery system.

Manages registration and lookup of NRS Access Point Providers.
Providers are discovered and registered at module load time.
"""

from typing import Dict, List, Optional, Type
import frappe
from .base import EInvoiceProvider

# Global registry of available providers
_PROVIDER_REGISTRY: Dict[str, Type[EInvoiceProvider]] = {}


def register_provider(provider_class: Type[EInvoiceProvider]) -> None:
	"""Register an access point provider.

	Called at module initialization to register built-in providers.
	Third-party providers can register themselves via hooks.

	Args:
		provider_class: Class inheriting from EInvoiceProvider.
				Must have a PROVIDER_NAME attribute.

	Raises:
		ValueError: If PROVIDER_NAME is not set or already registered.
	"""
	if not provider_class.PROVIDER_NAME:
		raise ValueError(f"Provider {provider_class.__name__} must set PROVIDER_NAME")

	if provider_class.PROVIDER_NAME in _PROVIDER_REGISTRY:
		frappe.logger("nrs_provider_registry").warning(
			f"Provider '{provider_class.PROVIDER_NAME}' already registered. Overwriting."
		)

	_PROVIDER_REGISTRY[provider_class.PROVIDER_NAME] = provider_class
	frappe.logger("nrs_provider_registry").info(
		f"Registered provider: {provider_class.PROVIDER_NAME} ({provider_class.__name__})"
	)


def get_provider(provider_name: str) -> Optional[Type[EInvoiceProvider]]:
	"""Get a provider class by name.

	Args:
		provider_name: Provider identifier (e.g., 'doftwerks', 'remita').

	Returns:
		Provider class if found, None otherwise.
	"""
	return _PROVIDER_REGISTRY.get(provider_name)


def get_all_providers() -> Dict[str, Type[EInvoiceProvider]]:
	"""Get all registered providers.

	Returns:
		Dict mapping provider names to provider classes.
	"""
	return _PROVIDER_REGISTRY.copy()


def list_provider_names() -> list[str]:
	"""Get list of registered provider names.

	Returns:
		Sorted list of provider identifiers.
	"""
	return sorted(_PROVIDER_REGISTRY.keys())


def instantiate_provider(
	provider_name: str,
	settings_doc: Optional[object] = None
) -> Optional[EInvoiceProvider]:
	"""Create an instance of a provider.

	Args:
		provider_name: Provider identifier.
		settings_doc: Optional settings document to pass to provider constructor.

	Returns:
		Provider instance if found, None otherwise.

	Raises:
		TypeError: If provider cannot be instantiated.
	"""
	provider_class = get_provider(provider_name)
	if not provider_class:
		frappe.logger("nrs_provider_registry").warning(
			f"Provider '{provider_name}' not found in registry"
		)
		return None

	try:
		# Try with settings_doc parameter
		if settings_doc:
			return provider_class(settings_doc)
		else:
			return provider_class()
	except TypeError:
		# Fall back to no-args constructor
		try:
			return provider_class()
		except Exception as e:
			frappe.logger("nrs_provider_registry").error(
				f"Failed to instantiate provider {provider_name}: {str(e)}"
			)
			raise TypeError(f"Cannot instantiate provider '{provider_name}': {str(e)}")


@frappe.whitelist()
def get_provider_credential_fields(provider: str) -> List[Dict]:
	"""Get credential field schema for a provider.

	Args:
		provider: Provider name (e.g., 'doftwerks')

	Returns:
		List of field schema dicts for the provider's credentials
	"""
	provider_class = get_provider(provider)
	if not provider_class:
		frappe.throw(f"Provider '{provider}' not found")
	
	# Instantiate without settings to get schema
	provider_instance = provider_class()
	return provider_instance.get_credential_fields()


# Register built-in providers
try:
	from .doftwerks import DoftwerksProvider
	register_provider(DoftwerksProvider)
except ImportError as e:
	frappe.logger("nrs_provider_registry").warning(
		f"Failed to import DoftwerksProvider: {str(e)}"
	)
