import io
import json
from django.test import TestCase

from .models import PartMaster, PartVersion, StockAlertSetting, StockHistory, SystemMaster
from .services import InputError, change_part, correct_movement, create_movement, inventory_rows, replace_alerts


class InventoryTests(TestCase):
    def setUp(self):
        self.system = SystemMaster.objects.create(name="制御A")
        self.other = SystemMaster.objects.create(name="制御B")
        self.part = PartMaster.objects.create(part_number="P100", model_number="V1", name="センサ")
        self.actor = {"operator": "担当者"}

    def movement(self, direction, quantity, system=None, part=None):
        return create_movement({
            "system_id": (system or self.system).id,
            "part_id": (part or self.part).id, "direction": direction,
            "quantity": quantity, **self.actor,
        })

    def test_company_is_not_required_for_movement_or_correction(self):
        first = self.movement("IN", 2)
        self.assertFalse(hasattr(StockHistory.objects.get(pk=first.pk), "company"))
        corrected = correct_movement(first.pk, {
            "direction": "IN", "quantity": 1,
            "note": "記載修正", "operator": "担当者",
        })
        self.assertEqual(corrected[1].operator, "担当者")
        self.assertEqual(inventory_rows()[0]["quantity"], 1)

    def test_system_separation_and_negative_block(self):
        self.movement("IN", 5)
        self.movement("OUT", 2)
        self.movement("IN", 4, system=self.other)
        rows = inventory_rows()
        self.assertEqual({r["system"]: r["quantity"] for r in rows}, {"制御A": 3, "制御B": 4})
        with self.assertRaises(InputError):
            self.movement("OUT", 4)
        self.assertEqual(StockHistory.objects.count(), 3)

    def test_zero_is_only_exported_if_monitored(self):
        self.movement("IN", 1)
        self.movement("OUT", 1)
        self.assertFalse(inventory_rows())
        replace_alerts(self.system, [{"part_id": self.part.id, "threshold": 2}])
        self.assertEqual(inventory_rows()[0]["quantity"], 0)
        self.assertTrue(inventory_rows()[0]["alert"])
        replace_alerts(self.system, [])
        self.assertFalse(inventory_rows())

    def test_positive_alerts_atomic(self):
        replace_alerts(self.system, [{"part_id": self.part.id, "threshold": 3}])
        with self.assertRaises(InputError):
            replace_alerts(self.system, [{"part_id": self.part.id, "threshold": 0}])
        self.assertEqual(StockAlertSetting.objects.get().threshold, 3)

    def test_part_version_keeps_id_and_ledger_snapshot(self):
        old = self.movement("IN", 3)
        change_part(self.part, {"part_number": "P200", "model_number": "V2", "name": "センサ2"})
        self.part.refresh_from_db()
        self.assertEqual(self.part.part_number, "P200")
        self.assertEqual(self.part.pk, old.part_id)
        self.assertEqual(StockHistory.objects.get(pk=old.pk).part_number_snapshot, "P100")
        self.assertEqual(PartVersion.objects.get().old_model_number, "V1")
        self.assertEqual(inventory_rows()[0]["quantity"], 3)

    def test_correction_is_append_only_and_cannot_breach_zero(self):
        original = self.movement("IN", 5)
        self.movement("OUT", 3)
        with self.assertRaises(InputError):
            correct_movement(original.pk, {"direction": "IN", "quantity": 2, "note": "誤記", **self.actor})
        self.assertEqual(StockHistory.objects.count(), 2)
        reverse, revised = correct_movement(
            original.pk, {"direction": "IN", "quantity": 4, "note": "誤記", **self.actor}
        )
        self.assertEqual(reverse.reversal_of_id, original.pk)
        self.assertEqual(revised.quantity, 4)
        self.assertEqual(inventory_rows()[0]["quantity"], 1)
        with self.assertRaises(InputError):
            correct_movement(original.pk, {"direction": "IN", "quantity": 4, "note": "重複", **self.actor})

    def test_excel_includes_zero_when_alerted(self):
        replace_alerts(self.system, [{"part_id": self.part.id, "threshold": 1}])
        response = self.client.get("/api/export")
        from openpyxl import load_workbook
        content = b"".join(response.streaming_content)
        ws = load_workbook(io.BytesIO(content)).active
        self.assertEqual(ws["E2"].value, 0)
        self.assertEqual(ws["G2"].value, "下限以下")

    def test_api_csrf_and_validation(self):
        client = self.client_class(enforce_csrf_checks=True)
        denied = client.post("/api/history", data="{}", content_type="application/json")
        self.assertEqual(denied.status_code, 403)
        client.get("/api/health")
        token = client.cookies["csrftoken"].value
        allowed = client.post(
            "/api/history", data=json.dumps({
                "system_id": self.system.id, "part_id": self.part.id,
                "direction": "OUT", "quantity": 1, **self.actor
            }), content_type="application/json", HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(allowed.status_code, 400)
