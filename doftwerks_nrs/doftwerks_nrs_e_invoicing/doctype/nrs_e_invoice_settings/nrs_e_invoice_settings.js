frappe.ui.form.on("NRS E-Invoice Settings", {
	refresh(frm) {
		const webhook_url =
			frappe.urllib.get_base_url() + "/api/method/doftwerks_nrs.einvoice.webhook";

		frm.set_intro(
			__("Webhook URL for the Access Point Provider portal (per environment): {0}", [
				`<code>${webhook_url}</code>`,
			]),
			"blue"
		);

		frm.add_custom_button(__("Copy Webhook URL"), () => {
			frappe.utils.copy_to_clipboard(webhook_url);
		});

		frm.add_custom_button(__("Test Connection"), () => {
			frappe.call({
				method: "doftwerks_nrs.einvoice.test_connection",
				freeze: true,
				freeze_message: __("Contacting the NRS Access Point..."),
				callback: (r) => {
					const rows = r.message || [];
					if (!rows.length) {
						frappe.msgprint({
							title: __("NRS Connection Test"),
							message: __("No billing entities configured yet. Add a row and save first."),
							indicator: "orange",
						});
						return;
					}
					const html = rows
						.map(
							(x) =>
								`${x.ok ? "✅" : "❌"} <strong>${frappe.utils.escape_html(x.company)}</strong>: ` +
								frappe.utils.escape_html(x.detail)
						)
						.join("<br>");
					frappe.msgprint({
						title: __("NRS Connection Test"),
						message: html,
						indicator: rows.every((x) => x.ok) ? "green" : "red",
					});
				},
			});
		});
	},

	provider(frm) {
		// Toggle legacy base_url field visibility
		const is_doftwerks = frm.doc.provider === "doftwerks";
		frm.toggle_display("base_url", is_doftwerks);
		
		// If provider changed, we might want to refresh billing entities table
		frm.refresh_field("billing_entities");
	},
});
