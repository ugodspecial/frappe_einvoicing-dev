# NRS E-Invoicing: Architecture Comparison

## Current Architecture (Doftwerks-Only)

```
┌─────────────────────────────────────────────────────────────────┐
│                     ERPNext ERP System                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Sales Invoice                                            │   │
│  │ - Customer, Items, Amounts                              │   │
│  │ - Hooks: on_submit → transmit_on_submit()              │   │
│  └────────────────────────▲─────────────────────────────────┘   │
└───────────────────────────┼─────────────────────────────────────┘
                            │ (IRN, Status, QR written back)
                            │
                    ┌───────▼────────┐
                    │  einvoice.py   │
                    │                │
                    │ transmit_      │
                    │ invoice()      │
                    │                │
                    │ build_         │
                    │ payload()      │
                    └───────┬────────┘
                            │ (Hardcoded to Doftwerks)
                            │
              ┌─────────────┴──────────────┐
              │  Doftwerks API Endpoint    │
              │  /api/v1/einvoice/transmit │
              │  (x-client-id header)      │
              └─────────────┬──────────────┘
                            │
                    ┌───────▼────────────┐
                    │ NRS Platform       │
                    │ (Nigeria Revenue   │
                    │  Service)          │
                    └────────────────────┘

PROBLEM: ❌ Tightly coupled to Doftwerks
         ❌ Difficult to add new providers
         ❌ Hard to test with different providers
         ❌ Requires code changes for each provider
```

---

## Target Architecture (Multi-Provider)

```
┌──────────────────────────────────────────────────────────────────┐
│                      ERPNext ERP System                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Sales Invoice                                              │  │
│  │ - Customer, Items, Amounts                                │  │
│  │ - Hooks: on_submit → transmit_on_submit()                │  │
│  └────────────────────────▲─────────────────────────────────┘  │
└───────────────────────────┼────────────────────────────────────┘
                            │ (IRN, Status, QR written back)
                            │
                ┌───────────▼──────────────┐
                │   einvoice.py (Refactored)│
                │                           │
                │  • transmit_invoice()     │
                │  • build_payload()        │ ← NRS-spec (unchanged)
                │  • _build_lines()         │ ← Validation (unchanged)
                │  • validate_invoice()     │ ← Pre-flight (unchanged)
                └───────────┬───────────────┘
                            │
                   ┌────────▼────────┐
                   │ Provider Layer  │
                   │ (New Interface) │
                   └────────┬────────┘
                            │
           ┌────────────────┼────────────────┐
           │                │                │
    ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
    │  Doftwerks  │  │   Remita    │  │   Other     │
    │  Provider   │  │  Provider   │  │  Provider   │
    │             │  │             │  │             │
    │ • transmit()│  │ • transmit()│  │ • transmit()│
    │ • webhook() │  │ • webhook() │  │ • webhook() │
    │ • validate_│  │ • validate_│  │ • validate_│
    │   creds()  │  │   creds()  │  │   creds()  │
    └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
           │                │                │
    ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
    │  Doftwerks  │  │   Remita    │  │   Other     │
    │   API       │  │    API      │  │   API       │
    └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
           │                │                │
           └────────────────┼────────────────┘
                            │
                    ┌───────▼────────┐
                    │ NRS Platform   │
                    │ (Nigeria       │
                    │  Revenue       │
                    │  Service)      │
                    └────────────────┘

BENEFITS: ✅ Loosely coupled provider architecture
          ✅ Add providers without touching core logic
          ✅ Easy to test each provider independently
          ✅ Support multiple providers in one deployment
          ✅ Backward compatible with existing Doftwerks setup
```

---

## Core vs. Provider-Specific Code

```
┌─────────────────────────────────────────────────────────────────┐
│ CORE CODE (NRS Specification - Provider-Agnostic)              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ • Invoice payload structure (tax codes, line items, totals)     │
│ • Validation rules (customer TIN, address, state/LGA)           │
│ • Invoice types (Invoice 381, Credit Note 380, Debit Note 384)  │
│ • Tax codes (STANDARD_VAT 7.5%, ZERO_VAT, EXEMPT_VAT)          │
│ • Line item building (HSN for goods, ISIC for services)         │
│ • Credit/debit note logic (reference original IRN)              │
│ • Payment status sync (PAID, PARTIAL, PENDING)                  │
│ • QR code attachment to invoice                                 │
│                                                                  │
│ These are the same regardless of which provider transmits.       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ PROVIDER-SPECIFIC CODE (Each provider implements)               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Doftwerks Provider:                                              │
│   • Endpoint: /api/v1/einvoice/transmit                          │
│   • Auth: x-client-id + x-client-secret headers                  │
│   • Credentials: client_id, client_secret, service_id            │
│   • Response parsing: Extract IRN from data.irn                  │
│   • Error patterns: "tax id", "mismatch", "billing_reference"    │
│   • Webhook: POST with signature verification                    │
│   • Status query: /api/v1/status endpoint                        │
│                                                                  │
│ Remita Provider (hypothetical):                                  │
│   • Endpoint: /api/2/einvoice/submit                             │
│   • Auth: Bearer token (OAuth)                                   │
│   • Credentials: api_key, merchant_id, certificate               │
│   • Response parsing: Extract invoice_ref from result.reference  │
│   • Error patterns: "INVALID_MERCHANT", "CERT_ERROR"             │
│   • Webhook: GET callback URL                                    │
│   • Status query: Query parameter with merchant_id               │
│                                                                  │
│ Each provider encapsulates these differences.                     │
│ Core logic remains untouched.                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Settings Structure Evolution

### Current (Single Provider)

```
NRS E-Invoice Settings
├── enabled: bool
├── auto_transmit_on_submit: bool
├── base_url: str  (Doftwerks only)
└── billing_entities: list
    └── company: "Test Entity Co"
        ├── client_id: "test-client"
        ├── client_secret: "***encrypted***"
        ├── service_id: "AB12CD34"
        └── supplier_* (TIN, email, address, etc.)
```

### Future (Multi-Provider)

```
NRS E-Invoice Settings
├── enabled: bool
├── auto_transmit_on_submit: bool
├── provider: "doftwerks"  ← NEW: Select provider
└── billing_entities: list
    └── company: "Test Entity Co"
        ├── provider: "doftwerks"  ← NEW: Can override globally selected provider
        ├── provider_credentials: {  ← NEW: JSON field (encrypted)
        │   "client_id": "test-client",
        │   "client_secret": "***encrypted***",
        │   "service_id": "AB12CD34",
        │   "base_url": "https://api.doftwerks.com"
        │ }
        └── supplier_* (TIN, email, address, etc.) ← UNCHANGED

E-Invoice Provider (New Master DocType)
├── name: "doftwerks"
├── title: "Doftwerks Access Point"
├── module: "doftwerks_nrs"
├── class_path: "doftwerks_nrs.providers.doftwerks.DoftwerksProvider"
├── is_active: 1
└── credential_schema: {  ← JSON describing required fields
    "fields": [
      {"fieldname": "client_id", "fieldtype": "Data", "required": 1},
      {"fieldname": "client_secret", "fieldtype": "Password", "required": 1},
      ...
    ]
  }
```

---

## Request/Response Flow: Before and After

### Current (Hardcoded)

```python
# einvoice.py - Line 183
def transmit_invoice(doc, settings=None):
    entity = _find_billing_entity(settings, doc.company)
    payload = build_payload(doc, entity, errors)
    
    # HARDCODED to Doftwerks
    url = f"{cstr(settings.base_url).rstrip('/')}/api/v1/einvoice/transmit"
    headers = {
        "x-client-id": entity.client_id,           # ← Doftwerks-specific
        "x-client-secret": entity.get_password("client_secret"),
        "Content-Type": "application/json",
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    _handle_response(doc, payload, response)  # ← Doftwerks-specific parsing
```

### Refactored (Provider-Agnostic)

```python
# einvoice.py - after refactoring
def transmit_invoice(doc, settings=None):
    settings = settings or frappe.get_single(SETTINGS_DOCTYPE)
    entity = _find_billing_entity(settings, doc.company)
    
    payload = build_payload(doc, entity, errors)  # ← NRS spec (unchanged)
    
    # NEW: Get appropriate provider
    provider = _get_provider(settings, entity)
    
    # Provider handles transmission, parsing, error messages
    result = provider.transmit(payload, entity.provider_credentials_json)
    
    # Standard result from any provider
    if result['success']:
        doc.db_set("nrs_irn", result['irn'])
        doc.db_set("nrs_receipt_status", result['status'])
        if result.get('qr_code'):
            _attach_qr_image(doc, result['qr_code'])
    else:
        doc.db_set("nrs_error", result['error'])
```

---

## File Structure: Before and After

### Before (Current)

```
doftwerks_nrs/
├── einvoice.py              (all logic tightly coupled)
├── hooks.py
├── doftwerks_nrs_e_invoicing/
│   ├── doctype/
│   │   ├── nrs_billing_entity/
│   │   │   ├── nrs_billing_entity.json
│   │   │   ├── nrs_billing_entity.py
│   │   │   └── nrs_billing_entity.js
│   │   └── nrs_e_invoice_settings/
│   │       ├── nrs_e_invoice_settings.json
│   │       ├── nrs_e_invoice_settings.py
│   │       └── nrs_e_invoice_settings.js
│   └── workspace/
└── tests/
    ├── test_einvoice.py
    └── utils.py
```

### After (Refactored)

```
doftwerks_nrs/
├── einvoice.py              (core logic only, provider-agnostic)
├── hooks.py
├── providers/               ← NEW: Provider implementations
│   ├── __init__.py         (registry)
│   ├── base.py             (abstract interface)
│   ├── doftwerks.py        (extracted from einvoice.py)
│   └── remita.py           (future: new provider example)
├── doftwerks_nrs_e_invoicing/
│   ├── doctype/
│   │   ├── e_invoice_provider/  ← NEW: Master DocType
│   │   │   ├── e_invoice_provider.json
│   │   │   └── e_invoice_provider.py
│   │   ├── nrs_billing_entity/
│   │   │   ├── nrs_billing_entity.json (updated)
│   │   │   ├── nrs_billing_entity.py (updated)
│   │   │   └── nrs_billing_entity.js
│   │   └── nrs_e_invoice_settings/
│   │       ├── nrs_e_invoice_settings.json (updated)
│   │       ├── nrs_e_invoice_settings.py (updated)
│   │       └── nrs_e_invoice_settings.js (updated)
│   └── workspace/
├── webhook.py              ← NEW: Provider-agnostic webhook router
└── tests/
    ├── test_providers.py    ← NEW: Provider tests
    ├── test_einvoice.py (refactored)
    ├── mock_provider.py     ← NEW: For testing
    └── utils.py
```

---

## Provider Registration Flow

```
Step 1: Provider Implementation
┌─────────────────────────────────────────┐
│ Create DoftwerksProvider class           │
│ Implement all abstract methods           │
│ from EInvoiceProvider                    │
└─────────────────────┬───────────────────┘

Step 2: Register in Hooks
┌─────────────────────────────────────────┐
│ hooks.py:                               │
│ fixtures = ["doftwerks_nrs/doctype/     │
│   e_invoice_provider/provider_data.json"]│
└─────────────────────┬───────────────────┘

Step 3: Create Provider Record
┌─────────────────────────────────────────┐
│ E-Invoice Provider doctype:             │
│ {                                       │
│   "name": "doftwerks",                  │
│   "title": "Doftwerks Access Point",   │
│   "class_path": "doftwerks_nrs.        │
│     providers.doftwerks.DoftwerksProvider"│
│ }                                       │
└─────────────────────┬───────────────────┘

Step 4: Select in Settings
┌─────────────────────────────────────────┐
│ NRS E-Invoice Settings form:            │
│ Provider: [Doftwerks Access Point]      │
│ ↓ (dynamically loads credential fields) │
│ Client ID: ___________                  │
│ Client Secret: ___________              │
│ Service ID: ___________                 │
└─────────────────────────────────────────┘

Step 5: Use Provider
┌─────────────────────────────────────────┐
│ On invoice submit:                      │
│ provider = get_provider("doftwerks")     │
│ result = provider.transmit(payload, creds)
│ ↓                                       │
│ Invoice updated with IRN/status         │
└─────────────────────────────────────────┘
```

---

## Error Handling: Before and After

### Before (Hardcoded Doftwerks Patterns)

```python
# einvoice.py - hardcoded error mappings
FRIENDLY_ERRORS = [
    ("mismatch", "NRS reports a TAX ID mismatch..."),
    ("tax id", "NRS reports a TAX ID mismatch..."),
    ("billing_reference", "The original invoice for this credit/debit note..."),
    ("hsn", "NRS rejected an item's classification..."),
    ("lga", "NRS rejected the customer's LGA code..."),
    # ... etc - all Doftwerks-specific
]

def _friendly_error(raw_message):
    for needle, guidance in FRIENDLY_ERRORS:
        if needle in raw_message.lower():
            return guidance
    return "Unknown error. Check NRS Error field."
```

**Problem**: If using a different provider, error messages may not match these patterns.

### After (Provider-Specific Error Handling)

```python
# providers/base.py
class EInvoiceProvider(ABC):
    @abstractmethod
    def transmit(self, payload, credentials):
        """
        Return:
        {
            'success': bool,
            'irn': str,
            'status': str,
            'qr_code': str,
            'error': str  ← Provider-specific friendly message
        }
        """
        pass

# providers/doftwerks.py
class DoftwerksProvider(EInvoiceProvider):
    FRIENDLY_ERRORS = [
        ("mismatch", "NRS reports a TAX ID mismatch..."),
        # ... etc
    ]
    
    def transmit(self, payload, credentials):
        response = requests.post(...)
        error_msg = self._friendly_error(response.text)
        return {
            'success': response.ok,
            'irn': data.get('irn'),
            'status': data.get('receipt_status'),
            'qr_code': data.get('qr_code'),
            'error': error_msg
        }
    
    def _friendly_error(self, raw_message):
        for needle, guidance in self.FRIENDLY_ERRORS:
            if needle in raw_message.lower():
                return guidance
        return "Check with Doftwerks support"

# providers/remita.py
class RemitaProvider(EInvoiceProvider):
    FRIENDLY_ERRORS = [
        ("INVALID_MERCHANT", "Remita: Merchant ID not recognized..."),
        # ... etc - Remita-specific
    ]
    
    def transmit(self, payload, credentials):
        # Remita-specific API call and error handling
        ...
```

**Benefit**: Each provider handles errors in its own context; core code unchanged.

---

## Summary of Changes

| Aspect | Current | After Refactoring |
|--------|---------|-------------------|
| **Supported Providers** | 1 (Doftwerks only) | ∞ (pluggable) |
| **Code Coupling** | Tightly coupled | Loosely coupled |
| **Adding Provider** | Modify core code | Create provider class |
| **Testing** | Mocked hardcoded | Mock any provider |
| **Error Handling** | Hardcoded strings | Provider-specific |
| **Settings** | Doftwerks-focused | Provider-agnostic |
| **Webhooks** | Hardcoded endpoint | Dynamic router |
| **Backward Compat** | N/A | Full compatibility |

---

## Next Steps

1. Review and approve this architecture
2. Begin Phase 1: Create provider base classes
3. Create issue tickets for each phase
4. Assign team members
5. Start development

