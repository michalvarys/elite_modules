"""The patient card client action is shipped in the backend assets (JS, templates, board patch)
and, where a Chrome is available, opens without JS errors."""
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPatientCardAssets(TransactionCase):

    def test_backend_bundle_contains_card(self):
        bundle = self.env["ir.qweb"]._get_asset_bundle("web.assets_backend", css=False, js=True)
        urls = [asset.url for asset in bundle.javascripts]
        self.assertTrue(any(u.endswith("elite_vet_clinic/static/src/patient_card/patient_card.js") for u in urls))
        self.assertTrue(any(u.endswith("elite_vet_clinic/static/src/board_patch/board_patch.js") for u in urls))
        templates = bundle.generate_xml_bundle()
        for name in ("elite_vet_clinic.PatientCard", "elite_vet_clinic.PatientSearch", "elite_vet_clinic.Picker"):
            self.assertIn(name, templates)
        # the board extension (t-inherit) with the "Karta" button
        self.assertIn("evpc-board-card", templates)

    def test_client_action(self):
        action = self.env.ref("elite_vet_clinic.action_patient_card")
        self.assertEqual(action.tag, "elite_vet_clinic.patient_card")


@tagged("post_install", "-at_install")
class TestPatientCardBrowser(HttpCase):
    """Skipped automatically when the test environment has no Chrome (e.g. the odoo:18 image)."""

    def test_start_screen_loads(self):
        code = """
            (async () => {
                for (let i = 0; i < 100; i++) {
                    if (document.querySelector('.evpc-start .evpc-search-input')) {
                        console.log('test successful');
                        return;
                    }
                    await new Promise((r) => setTimeout(r, 100));
                }
                console.error('patient card start screen did not render');
            })();
        """
        self.browser_js("/odoo/action-elite_vet_clinic.action_patient_card", code, login="admin")
