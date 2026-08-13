function nrs_lookup_dialog(title, url) {
	const d = new frappe.ui.Dialog({ title: title, size: "extra-large" });
	d.$body.html(
		`<iframe src="${url}" style="width: 100%; height: 70vh; border: 0;"></iframe>` +
		`<div style="margin-top: 8px;"><a href="${url}" target="_blank">${__("Open in new tab")}</a></div>`
	);
	d.show();
}

frappe.ui.form.on("Customer", {
	refresh(frm) {
		frm.add_custom_button(__("Find State / LGA Code"), () => {
			nrs_lookup_dialog(__("NRS State / LGA Code Lookup"), "https://web-tab.netlify.app/state-lga.html");
		});
	},
});
