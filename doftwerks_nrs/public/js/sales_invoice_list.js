// Surface NRS transmission problems in the Sales Invoice list view.
// Loads after ERPNext's listview settings (app load order), so we wrap the
// existing get_indicator instead of replacing the whole settings object.
(function () {
	const settings =
		frappe.listview_settings["Sales Invoice"] ||
		(frappe.listview_settings["Sales Invoice"] = {});

	settings.add_fields = (settings.add_fields || []).concat([
		"nrs_receipt_status",
		"nrs_irn",
	]);

	const original_get_indicator = settings.get_indicator;

	settings.get_indicator = function (doc) {
		if (doc.docstatus === 1) {
			const status = doc.nrs_receipt_status;
			if (status === "REJECTED" || status === "FAILED") {
				return [
					__("NRS {0}", [status]),
					"red",
					"nrs_receipt_status,=," + status,
				];
			}
		}
		return original_get_indicator ? original_get_indicator(doc) : undefined;
	};
})();
