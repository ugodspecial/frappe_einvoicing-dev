# NRS E-Invoicing: Multi-Provider Refactoring Plan

## Executive Summary

This document outlines the refactoring strategy to transform the Doftwerks NRS E-Invoicing app from a **single-provider solution** into a **flexible, multi-provider platform** that supports any NRS-compliant Access Point Provider (APP).

**Current State**: Code is tightly coupled to Doftwerks' API and authentication model.  
**Target State**: Pluggable provider architecture that allows switching between or using multiple providers.

---

## Part 1: Current Architecture Analysis

### 1.1 Current Stack (Doftwerks Only)

```
ERPNext Sales Invoice
        ↓
   einvoice.py (transmit_on_submit hook)
        ↓
   Doftwerks Access Point API (hardcoded)
        ↓
   NRS Platform
```

### 1.2 Core Components

#### **einvoice.py** (Main transmission engine)
- **Line 183-220**: `transmit_invoice()` - Main transmission function
  - Hardcoded base URL: `settings.base_url` (but controlled by settings)
  - Hardcoded headers: `x-client-id`, `x-client-secret`
  - Request timeout: 30 seconds
  - POST to `/api/v1/einvoice/transmit`

- **Line 223-300**: `build_payload()` - Creates NRS-compliant invoice payload
  - Validates customer data (TIN, address, state/LGA)
  - Builds invoice line items
  - Structures data per NRS spec (not provider-specific)

- **Line 303-345**: `_build_lines()` - Invoice line building
  - Handles goods (HSN codes) and services (ISIC codes)
  - Tax calculation per NRS rates

- **Line 413-465**: `_handle_response()` - Parses Doftwerks response
  - Extracts IRN, receipt_status, QR code
  - Writes to invoice via `db_set()`

#### **nrs_e_invoice_settings.py** (Configuration storage)
```python
class NRSEInvoiceSettings(Document):
    auto_transmit_on_submit: bool
    base_url: str          # "Provider-agnostic" (but only used for Doftwerks)
    enabled: bool
    billing_entities: Table[NRSBillingEntity]
```

#### **nrs_billing_entity DocType** (Per-company credentials)
- `company` - ERPNext company link
- `client_id` - Doftwerks client ID
- `client_secret` - Encrypted password field
- `service_id` - Doftwerks service identifier
- `supplier_*` - Supplier details (TIN, email, address, etc.)

#### **nrs_e_invoice_settings.js** (UI)
- Test Connection button calls `doftwerks_nrs.einvoice.test_connection`
- Webhook URL display (hardcoded to `doftwerks_nrs.einvoice.webhook`)

---

## Part 2: Provider Abstraction Design

### 2.1 What Varies Between Providers?

| Aspect | Doftwerks | Other APPs | Notes |
|--------|-----------|-----------|-------|
| **Endpoint URL** | `{base_url}/api/v1/einvoice/transmit` | Varies | Can be configurable |
| **Auth Headers** | `x-client-id`, `x-client-secret` | Varies | May use JWT, API keys, OAuth, etc. |
| **Request Format** | JSON POST | Likely JSON | NRS payload is standard |
| **Response Format** | `{data: {irn, receipt_status, qr_code}, message: str}` | May differ | Need to extract IRN, status, QR |
| **Credentials Storage** | `client_id`, `client_secret` | Varies | Provider may need API key, cert, token, etc. |
| **Error Messages** | Specific error patterns | Varies | May not follow Doftwerks conventions |
| **Webhook Support** | `doftwerks_nrs.einvoice.webhook` | Varies | URL pattern provider-specific |
| **Status Polling** | Required fallback | Varies | Query format provider-specific |

### 2.2 What's Provider-Agnostic?

✅ **NRS Specification** (Universal):
- Invoice payload structure (ISICs, HSNs, tax codes, etc.)
- Validation rules (customer TIN, address, etc.)
- Receipt types (Invoice, Credit Note, Debit Note)
- Tax codes (STANDARD_VAT, REDUCED_VAT, etc.)

✅ **Core Business Logic**:
- Pre-flight validation (customers, items, addresses)
- Payload building from Sales Invoice
- Invoice submission hook
- QR code attachment
- Credit/debit note handling

❌ **Provider-Specific**:
- Transmission mechanism
- Credential management
- Response parsing
- Error handling
- Webhook processing
- Status polling

---

## Part 3: Target Architecture

### 3.1 Provider Interface

```python
# providers/base.py
class EInvoiceProvider(ABC):
    """Abstract base for NRS Access Point Providers."""
    
    PROVIDER_NAME: str  # e.g., "doftwerks", "remita", etc.
    
    @abstractmethod
    def validate_credentials(self, credentials: dict) -> tuple[bool, str]:
        """Test connection. Return (success, message)."""
        pass
    
    @abstractmethod
    def transmit(self, payload: dict, credentials: dict) -> dict:
        """
        Transmit invoice to NRS via this provider.
        Return: {success: bool, irn: str, status: str, qr_code: str, error: str}
        """
        pass
    
    @abstractmethod
    def parse_response(self, response: requests.Response) -> dict:
        """Parse provider-specific response into standard format."""
        pass
    
    @abstractmethod
    def get_credential_fields(self) -> list[dict]:
        """Return list of credential field schemas for UI."""
        pass
    
    @abstractmethod
    def handle_webhook(self, payload: dict, signature: str) -> dict:
        """Verify and process webhook from provider."""
        pass
    
    @abstractmethod
    def query_status(self, irn: str, credentials: dict) -> dict:
        """Poll provider for invoice status. Return {status: str, error: str}."""
        pass
```

### 3.2 Doftwerks Implementation

```python
# providers/doftwerks.py
class DoftwerksProvider(EInvoiceProvider):
    PROVIDER_NAME = "doftwerks"
    
    def validate_credentials(self, credentials):
        # POST to /api/v1/test with client_id, client_secret
        # Return success/failure
        pass
    
    def transmit(self, payload, credentials):
        # POST to /api/v1/einvoice/transmit with x-client-id header
        # Parse response for IRN, receipt_status, qr_code
        pass
    
    def parse_response(self, response):
        # Handle Doftwerks-specific response format
        pass
    
    def get_credential_fields(self):
        return [
            {"fieldname": "client_id", "label": "Client ID", "fieldtype": "Data"},
            {"fieldname": "client_secret", "label": "Client Secret", "fieldtype": "Password"},
            {"fieldname": "service_id", "label": "Service ID", "fieldtype": "Data"},
        ]
    
    def handle_webhook(self, payload, signature):
        # Verify Doftwerks webhook signature
        # Return parsed data
        pass
    
    def query_status(self, irn, credentials):
        # Query /api/v1/status endpoint
        pass
```

### 3.3 Updated NRS E-Invoice Settings

```python
# nrs_e_invoice_settings.json
{
    "enabled": true,
    "provider": "doftwerks",  # New field: select from registered providers
    "billing_entities": [
        {
            "company": "Test Entity Co",
            "provider_credentials": {...},  # JSON field with provider-specific creds
            "supplier_tin": "00000000-0001",
            # ... other supplier details
        }
    ]
}
```

### 3.4 Updated Billing Entity DocType

```python
# nrs_billing_entity.json - Add new fields
{
    "fieldname": "provider",
    "label": "Provider",
    "fieldtype": "Link",
    "options": "E-Invoice Provider",  # New DocType linking to registered providers
}
{
    "fieldname": "provider_credentials_json",
    "label": "Provider Credentials",
    "fieldtype": "JSON",
    "description": "Provider-specific credentials (encrypted)"
}
```

### 3.5 New: E-Invoice Provider DocType (Master)

Centralized provider registration:
```
E-Invoice Provider
├── name (provider_key: "doftwerks", "remita", etc.)
├── title (display name)
├── module (app name, e.g., "doftwerks_nrs")
├── class_path (e.g., "doftwerks_nrs.providers.doftwerks.DoftwerksProvider")
├── is_active
└── doc_fields (JSON schema for credential fields)
```

---

## Part 4: Refactoring Implementation Steps

### Step 1: Create Provider Architecture

**File**: `doftwerks_nrs/providers/base.py`
```python
# ABC for all providers
from abc import ABC, abstractmethod

class EInvoiceProvider(ABC):
    PROVIDER_NAME = None
    
    @abstractmethod
    def validate_credentials(self, credentials: dict) -> tuple[bool, str]:
        pass
    
    @abstractmethod
    def transmit(self, payload: dict, credentials: dict) -> dict:
        pass
    
    # ... (other abstract methods)
```

**File**: `doftwerks_nrs/providers/doftwerks.py`
```python
# Extract all existing Doftwerks logic here
from .base import EInvoiceProvider

class DoftwerksProvider(EInvoiceProvider):
    PROVIDER_NAME = "doftwerks"
    
    def __init__(self, settings_doc):
        self.settings = settings_doc
    
    # Move transmit_invoice, _handle_response, etc. here
```

### Step 2: Create Provider Registry

**File**: `doftwerks_nrs/providers/__init__.py`
```python
# Provider discovery and registration
PROVIDERS = {}

def register_provider(provider_class):
    PROVIDERS[provider_class.PROVIDER_NAME] = provider_class

def get_provider(provider_name):
    return PROVIDERS.get(provider_name)

register_provider(DoftwerksProvider)
```

### Step 3: Refactor einvoice.py

**Current**:
```python
def transmit_invoice(doc, settings=None):
    # ... build payload ...
    response = requests.post(url, json=payload, headers=headers, ...)
    _handle_response(doc, payload, response)
```

**Refactored**:
```python
def transmit_invoice(doc, settings=None):
    provider = _get_provider(settings)
    payload = build_payload(doc, entity, errors)  # Still here - NRS spec
    result = provider.transmit(payload, entity.provider_credentials)
    
    if result['success']:
        doc.db_set("nrs_irn", result['irn'])
        doc.db_set("nrs_receipt_status", result['status'])
        if result['qr_code']:
            _attach_qr_image(doc, result['qr_code'])
    else:
        doc.db_set("nrs_error", result['error'])
```

### Step 4: Update Settings DocType

Add fields:
- `provider` - Link to E-Invoice Provider (default "doftwerks")
- Migrate existing `base_url` to provider-specific config

### Step 5: Update UI

**nrs_e_invoice_settings.js**:
```javascript
frappe.ui.form.on("NRS E-Invoice Settings", {
    on_load(frm) {
        // Load provider-specific credential fields dynamically
    },
    
    provider: {
        change(frm) {
            // Update credential fields based on selected provider
            frappe.call({
                method: "doftwerks_nrs.providers.get_provider_config",
                args: {provider: frm.doc.provider},
                callback: (r) => {
                    update_credential_fields(frm, r.message);
                }
            });
        }
    }
});
```

### Step 6: Webhook Abstraction

**Current**: Hardcoded `doftwerks_nrs.einvoice.webhook`

**Refactored**:
```python
# doftwerks_nrs/webhook.py
@frappe.whitelist(allow_guest=True)
def handle_webhook():
    """Route webhooks to appropriate provider."""
    settings = frappe.get_single("NRS E-Invoice Settings")
    provider = _get_provider(settings)
    
    payload = frappe.request.get_json()
    signature = frappe.request.headers.get("X-Signature")
    
    result = provider.handle_webhook(payload, signature)
    # Update invoice status
```

---

## Part 5: Migration & Backward Compatibility

### 5.1 Data Migration

On first load after upgrade:
```python
# migration script
def migrate_existing_settings():
    """Convert Doftwerks settings to provider model."""
    settings = frappe.get_single("NRS E-Invoice Settings")
    
    if not settings.provider:
        settings.provider = "doftwerks"  # Default to Doftwerks
        
        # Migrate billing entities
        for entity in settings.billing_entities:
            if not entity.provider:
                entity.provider = "doftwerks"
                entity.provider_credentials_json = json.dumps({
                    "client_id": entity.client_id,
                    "client_secret": entity.get_password("client_secret"),
                    "service_id": entity.service_id,
                    "base_url": settings.base_url,  # Store URL per entity
                })
            entity.client_id = ""  # Clear old fields
            # ...
    
    settings.save()
```

### 5.2 Fallback Logic

If no provider is configured, default to Doftwerks for backward compatibility.

---

## Part 6: Adding New Providers

Example: Adding **Remita** as a provider

```python
# doftwerks_nrs/providers/remita.py
class RemitaProvider(EInvoiceProvider):
    PROVIDER_NAME = "remita"
    
    def validate_credentials(self, credentials):
        # Remita-specific test logic
        pass
    
    def transmit(self, payload, credentials):
        # POST to Remita endpoint with their auth method
        # Parse their response format
        return {
            'success': True/False,
            'irn': extracted_irn,
            'status': extracted_status,
            'qr_code': extracted_qr,
            'error': error_message_if_failed
        }
    
    # ... implement other abstract methods
```

Then register:
```python
# In doftwerks_nrs/providers/__init__.py or hooks
register_provider(RemitaProvider)
```

---

## Part 7: Testing Strategy

### 7.1 Unit Tests

```python
# doftwerks_nrs/tests/test_providers.py
def test_doftwerks_transmit():
    """Test Doftwerks provider transmission."""
    provider = DoftwerksProvider(settings_doc)
    result = provider.transmit(payload, credentials)
    assert result['success']
    assert result['irn']

def test_provider_registry():
    """Test provider registration."""
    provider = get_provider("doftwerks")
    assert provider is not None
```

### 7.2 Mock Providers

```python
# doftwerks_nrs/tests/mock_providers.py
class MockProvider(EInvoiceProvider):
    """For testing without hitting actual APIs."""
    PROVIDER_NAME = "mock"
    
    def transmit(self, payload, credentials):
        return {
            'success': True,
            'irn': f"MOCK-{payload['invoice_number']}",
            'status': "TRANSMITTED",
            'qr_code': None,
            'error': None
        }
```

---

## Part 8: Configuration Across Environments

### 8.1 Multi-Environment Setup

```python
# For companies needing different providers per environment:

# Production
Provider: doftwerks
Base URL: https://api.doftwerks.com
Client ID: prod-client-id

# Staging
Provider: doftwerks
Base URL: https://staging-api.doftwerks.com
Client ID: staging-client-id

# OR if using different provider for staging:
Provider: remita (test environment)
API Key: test-api-key
```

---

## Part 9: Documentation for Providers

### 9.1 Provider Integration Guide

Create `docs/PROVIDER_DEVELOPMENT.md`:

```markdown
# Developing an E-Invoice Provider

## Requirements
1. Inherit from `EInvoiceProvider`
2. Implement all abstract methods
3. Handle NRS payload structure (unchanged)
4. Return standardized result dict
5. Register provider in module hooks

## Example: Remita Provider

[Full code example]

## Testing Your Provider

1. Create mock response fixtures
2. Write unit tests
3. Test with test environment credentials
4. Register in test suite
```

---

## Part 10: Phased Rollout

### Phase 1: Foundation (Week 1)
- ✅ Create `providers/base.py` and `providers/__init__.py`
- ✅ Extract Doftwerks to `providers/doftwerks.py`
- ✅ Create provider registry
- ✅ Update `einvoice.py` to use provider interface

### Phase 2: Settings & UI (Week 2)
- ✅ Add provider field to NRS E-Invoice Settings
- ✅ Create E-Invoice Provider master DocType
- ✅ Update settings UI to be provider-aware
- ✅ Add provider-specific credential fields
- ✅ Create migration script

### Phase 3: Testing & QA (Week 3)
- ✅ Write provider interface tests
- ✅ Write Doftwerks provider tests
- ✅ Create mock provider for testing
- ✅ Manual testing with existing Doftwerks setup
- ✅ Verify backward compatibility

### Phase 4: Documentation & Release (Week 4)
- ✅ Write provider development guide
- ✅ Document provider API contract
- ✅ Create example: second provider (Remita or mock)
- ✅ Update README with multi-provider info
- ✅ Release v2.0

---

## Part 11: Benefits of Refactoring

| Benefit | Impact |
|---------|--------|
| **Flexibility** | Add new providers without modifying core logic |
| **Maintainability** | Each provider isolated; easier to debug |
| **Scalability** | Handle multiple providers per deployment |
| **Testing** | Mock providers for unit tests |
| **Vendor Independence** | Not locked into Doftwerks |
| **Future-Proof** | Ready for NRS platform changes or alternatives |

---

## Part 12: Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing installations | Backward compatibility layer + migration script |
| Doftwerks credentials leaking during migration | Encrypt credentials field; validate during migration |
| Complex provider interface | Start simple; extend as needed; document well |
| Provider bugs affecting other providers | Isolation + per-provider error handling + logging |

---

## Appendix A: Current Code Locations

| Component | File | Lines |
|-----------|------|-------|
| Main transmission | `einvoice.py` | 183-220 |
| Payload building | `einvoice.py` | 223-300 |
| Line building | `einvoice.py` | 303-345 |
| Response handling | `einvoice.py` | 413-465 |
| QR attachment | `einvoice.py` | 468-485 |
| Settings DocType | `nrs_e_invoice_settings.py` | 1-25 |
| Settings UI | `nrs_e_invoice_settings.js` | 1-50 |
| Billing entity | `nrs_billing_entity/*.json` | - |
| Tests | `tests/test_einvoice.py` | 1-100+ |

---

## Appendix B: Key Constants to Preserve

```python
# These are NRS-spec, provider-agnostic
INVOICE_TYPE_CODES = {
    "Invoice": "381",
    "Credit Note": "380",
    "Debit Note": "384",
}

TAX_RATES = {
    "STANDARD_VAT": 7.5,
    "REDUCED_VAT": 0.0,
    "ZERO_VAT": 0.0,
    "EXEMPT_VAT": 0.0,
}

RECEIPT_STATUS_LABELS = {
    1: "INITIATED",
    2: "SIGNED",
    3: "TRANSMITTING",
    4: "TRANSMITTED",
}

# These MOVE to provider layer
DOFTWERKS_REQUEST_TIMEOUT = 30
DOFTWERKS_API_ENDPOINT = "/api/v1/einvoice/transmit"
DOFTWERKS_HEADERS = ["x-client-id", "x-client-secret"]
```

---

## Appendix C: Example: Provider Configuration in Frappe

```json
{
  "doctype": "E-Invoice Provider",
  "name": "doftwerks",
  "title": "Doftwerks Access Point",
  "is_active": 1,
  "class_path": "doftwerks_nrs.providers.doftwerks.DoftwerksProvider",
  "credential_schema": {
    "fields": [
      {
        "fieldname": "client_id",
        "label": "Client ID",
        "fieldtype": "Data",
        "required": 1
      },
      {
        "fieldname": "client_secret",
        "label": "Client Secret",
        "fieldtype": "Password",
        "required": 1
      },
      {
        "fieldname": "service_id",
        "label": "Service ID",
        "fieldtype": "Data",
        "required": 1
      },
      {
        "fieldname": "base_url",
        "label": "API Base URL",
        "fieldtype": "Data",
        "default": "https://api.doftwerks.com"
      }
    ]
  }
}
```

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Approve target architecture**
3. **Allocate resources** for phased implementation
4. **Create GitHub issues** for each phase
5. **Begin Phase 1: Foundation**

