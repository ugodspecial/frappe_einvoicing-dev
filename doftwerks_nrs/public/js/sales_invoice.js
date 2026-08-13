frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || frm.doc.nrs_irn) {
			return;
		}

		const status = frm.doc.nrs_receipt_status;
		const label =
			status === "REJECTED" || status === "FAILED"
				? __("Retry NRS Transmission")
				: __("Transmit to NRS");

		frm.add_custom_button(label, () => {
			frappe.call({
				method: "doftwerks_nrs.einvoice.retry_transmission",
				args: { name: frm.doc.name },
				freeze: true,
				freeze_message: __("Transmitting to NRS..."),
				callback: (r) => {
					const res = r.message || {};
					frm.reload_doc();
					if (res.irn) {
						frappe.show_alert({
							message: __("Transmitted to NRS. IRN: {0}", [res.irn]),
							indicator: "green",
						});
					} else {
						frappe.msgprint({
							title: __("NRS Transmission"),
							message: frappe.utils.escape_html(
								res.error || __("Invoice was not transmitted. Check NRS E-Invoice Settings.")
							),
							indicator: "red",
						});
					}
				},
			});
		});
	},
});
