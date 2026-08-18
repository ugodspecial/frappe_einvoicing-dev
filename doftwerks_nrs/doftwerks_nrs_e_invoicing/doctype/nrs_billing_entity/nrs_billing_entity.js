frappe.ui.form.on("NRS Billing Entity", {
	form_render(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		// Show/hide legacy Doftwerks fields based on provider
		toggle_doftwerks_fields(frm, row);
		
		// If provider_credentials_json exists, show a summary
		if (row.provider_credentials_json) {
			show_credentials_summary(frm, row);
		}
		
		// For non-Doftwerks providers, load dynamic credential fields
		if (row.provider && row.provider !== "doftwerks") {
			load_credential_fields(frm, row);
		}
	},
	
	provider(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		toggle_doftwerks_fields(frm, row);
		update_credential_fields(frm, row);
	}
});

function toggle_doftwerks_fields(frm, row) {
	const is_doftwerks = row.provider === "doftwerks";
	
	// Toggle legacy section and fields in the child dialog
	frm.fields_dict.billing_entities.grid.toggle_enable("client_id", is_doftwerks);
	frm.fields_dict.billing_entities.grid.toggle_enable("client_secret", is_doftwerks);
	frm.fields_dict.billing_entities.grid.toggle_enable("business_id", is_doftwerks);
	
	// In the child form dialog, we can also use grid's form fields toggle
	const grid_row = frm.fields_dict.billing_entities.grid.get_row(row.name);
	if (grid_row && grid_row.form) {
		grid_row.form.toggle_display("doftwerks_section", is_doftwerks);
		grid_row.form.toggle_display("client_id", is_doftwerks);
		grid_row.form.toggle_display("client_secret", is_doftwerks);
		grid_row.form.toggle_display("business_id", is_doftwerks);
		grid_row.form.toggle_display("provider_credentials_json", !is_doftwerks);
	}
}

function show_credentials_summary(frm, row) {
	try {
		const creds = JSON.parse(row.provider_credentials_json);
		const keys = Object.keys(creds).filter(k => !k.includes("secret") && !k.includes("password"));
		if (keys.length > 0) {
			const grid_row = frm.fields_dict.billing_entities.grid.get_row(row.name);
			if (grid_row && grid_row.form) {
				grid_row.form.set_intro(
					__("Provider credentials configured: {0}", [keys.join(", ")]),
					"green"
				);
			}
		}
	} catch (e) {
		// Invalid JSON, ignore
	}
}

function load_credential_fields(frm, row) {
	if (!row.provider || row.provider === "doftwerks") return;
	
	frappe.call({
		method: "doftwerks_nrs.providers.get_provider_credential_fields",
		args: { provider: row.provider },
		callback: (r) => {
			if (r.message) {
				render_credential_form(frm, row, r.message);
			}
		}
	});
}

function update_credential_fields(frm, row) {
	if (row.provider !== "doftwerks" && row.provider) {
		// For non-Doftwerks providers, load dynamic fields
		frappe.call({
			method: "doftwerks_nrs.providers.get_provider_credential_fields",
			args: { provider: row.provider },
			callback: (r) => {
				if (r.message) {
					render_credential_form(frm, row, r.message);
				}
			}
		});
	}
}

function render_credential_form(frm, row, fields) {
	const grid_row = frm.fields_dict.billing_entities.grid.get_row(row.name);
	if (!grid_row || !grid_row.form) return;
	
	const creds_field = grid_row.form.get_field("provider_credentials_json");
	if (!creds_field) return;
	
	// Parse existing credentials
	let existing_creds = {};
	try {
		if (row.provider_credentials_json) {
			existing_creds = JSON.parse(row.provider_credentials_json);
		}
	} catch (e) {
		// Invalid JSON, start fresh
	}
	
	// Build a description with field information
	let description = "<div class='provider-credential-fields'><strong>Required Fields:</strong><ul>";
	fields.forEach(field => {
		const value = existing_creds[field.fieldname] ? "✓ Set" : "✗ Required";
		const field_type = field.fieldtype || "Data";
		const required = field.required ? " (required)" : "";
		description += `<li><code>${field.fieldname}</code> - ${field.label} [${field_type}]${required}: ${value}</li>`;
	});
	description += "</ul></div>";
	
	// Add a note about editing via JSON
	description += "<small>Edit the JSON field directly to add/update credentials. Password fields will be encrypted.</small>";
	
	// Update the field's description
	creds_field.df.description = description;
	grid_row.form.refresh_field("provider_credentials_json");
}
