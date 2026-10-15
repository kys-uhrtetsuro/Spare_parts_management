import io
import json
from django.test import TestCase

from .models import EquipmentMaster, EquipmentSection, PartCategory, PartMaster, PartVersion, StockAlertSetting, StockHistory, SystemMaster, SystemPartPlacement
from .services import InputError, change_part, correct_movement, create_movement, inventory_rows, replace_alerts, create_part


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

    def test_alert_remains_on_older_stock_then_transfers_on_successor_stock(self):
        self.movement("IN", 5)
        replace_alerts(self.system, [{"part_id": self.part.pk, "threshold": 3}])
        successor = change_part(self.part, {
            "part_number": "P200", "model_number": "V2", "name": "更新品",
        })
        self.assertEqual(
            list(StockAlertSetting.objects.values_list("part_id", "threshold")),
            [(self.part.pk, 3)],
        )
        self.movement("OUT", 2)
        self.assertEqual(
            list(StockAlertSetting.objects.values_list("part_id", "threshold")),
            [(self.part.pk, 3)],
        )
        self.movement("IN", 2, part=successor)
        self.assertEqual(
            list(StockAlertSetting.objects.values_list("part_id", "threshold")),
            [(successor.pk, 3)],
        )
        old = next(row for row in inventory_rows(self.system.pk)
                   if row["part_id"] == self.part.pk)
        self.assertEqual((old["quantity"], old["threshold"]), (3, None))
        new = next(row for row in inventory_rows(self.system.pk)
                   if row["part_id"] == successor.pk)
        self.assertEqual((new["quantity"], new["threshold"]), (2, 3))
        self.assertEqual(StockAlertSetting.objects.count(), 1)

    def test_obsolete_alert_drops_at_zero_without_successor_stock(self):
        self.movement("IN", 2)
        replace_alerts(self.system, [{"part_id": self.part.pk, "threshold": 3}])
        successor = change_part(self.part, {
            "part_number": "P200", "model_number": "V1", "name": "現行品",
        })
        self.movement("OUT", 2)
        self.assertFalse(StockAlertSetting.objects.exists())
        self.assertFalse(inventory_rows(self.system.pk))
        self.movement("IN", 1, part=successor)
        self.assertFalse(StockAlertSetting.objects.exists())

    def test_new_alert_for_obsolete_part_is_rejected_atomically(self):
        self.movement("IN", 5)
        successor = change_part(self.part, {
            "part_number": "P200", "model_number": "V2", "name": "新型",
        })
        replace_alerts(self.system, [{"part_id": successor.pk, "threshold": 4}])
        with self.assertRaisesRegex(InputError, "後継登録済み"):
            replace_alerts(self.system, [{"part_id": self.part.pk, "threshold": 2}])
        self.assertEqual(
            list(StockAlertSetting.objects.values_list("part_id", "threshold")),
            [(successor.pk, 4)],
        )
        response = self.client.post(
            "/api/alerts/bulk", content_type="application/json",
            data=json.dumps({
                "system_id": self.system.pk,
                "items": [{"part_id": self.part.pk, "threshold": 2}],
            }),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StockAlertSetting.objects.get().part_id, successor.pk)

    def test_existing_obsolete_alert_is_read_only_and_newer_explicit_wins(self):
        self.movement("IN", 5)
        replace_alerts(self.system, [{"part_id": self.part.pk, "threshold": 3}])
        successor = change_part(self.part, {
            "part_number": "P200", "model_number": "V2", "name": "新型",
        })
        # Existing threshold can be included unchanged in an ordinary bulk save.
        self.assertEqual(replace_alerts(
            self.system, [{"part_id": self.part.pk, "threshold": 3}]
        ), 1)
        with self.assertRaisesRegex(InputError, "後継登録済み"):
            replace_alerts(self.system, [{"part_id": self.part.pk, "threshold": 5}])
        replace_alerts(self.system, [
            {"part_id": self.part.pk, "threshold": 3},
            {"part_id": successor.pk, "threshold": 6},
        ])
        self.assertEqual(
            list(StockAlertSetting.objects.values_list("part_id", "threshold")),
            [(successor.pk, 6)],
        )

    def test_alert_reconciliation_is_scoped_to_system_and_full_lineage(self):
        self.movement("IN", 5)
        self.movement("IN", 4, system=self.other)
        replace_alerts(self.system, [{"part_id": self.part.pk, "threshold": 2}])
        replace_alerts(self.other, [{"part_id": self.part.pk, "threshold": 9}])
        middle = change_part(self.part, {
            "part_number": "P100", "model_number": "V2", "name": "中間品",
        })
        latest = change_part(middle, {
            "part_number": "P200", "model_number": "V3", "name": "現行品",
        })
        self.movement("IN", 3, part=latest)
        self.assertEqual(
            list(StockAlertSetting.objects.filter(system=self.system).values_list(
                "part_id", "threshold"
            )), [(latest.pk, 2)]
        )
        self.assertEqual(
            list(StockAlertSetting.objects.filter(system=self.other).values_list(
                "part_id", "threshold"
            )), [(self.part.pk, 9)]
        )
        self.movement("IN", 1, part=latest, system=self.other)
        self.assertEqual(
            list(StockAlertSetting.objects.filter(system=self.other).values_list(
                "part_id", "threshold"
            )), [(latest.pk, 9)]
        )

    def test_correcting_old_history_to_zero_retires_old_alert(self):
        initial = self.movement("IN", 2)
        replace_alerts(self.system, [{"part_id": self.part.pk, "threshold": 3}])
        change_part(self.part, {
            "part_number": "P200", "model_number": "V2", "name": "新型",
        })
        correct_movement(initial.id, {
            "direction": "IN", "quantity": 1, "operator": "担当者",
            "note": "数量を1に訂正",
        })
        self.assertTrue(StockAlertSetting.objects.exists())
        self.movement("OUT", 1)
        self.assertFalse(StockAlertSetting.objects.exists())

    def test_successor_keeps_old_identifier_and_its_stock(self):
        old = self.movement("IN", 3)
        successor = change_part(self.part, {
            "part_number": "P200", "model_number": "V2", "name": "センサ2",
        })
        self.assertNotEqual(successor.id, self.part.id)
        self.assertEqual(successor.previous_part_id, self.part.id)
        self.assertEqual((self.part.part_number, self.part.model_number), ("P100", "V1"))
        history = StockHistory.objects.get(pk=old.pk)
        self.assertEqual((history.part_id, history.part_number_snapshot), (self.part.id, "P100"))
        self.assertEqual(inventory_rows()[0]["part_number"], "P100")
        self.movement("IN", 2, part=successor)
        self.assertEqual(
            {r["part_number"]: r["quantity"] for r in inventory_rows()},
            {"P100": 3, "P200": 2},
        )
        self.assertEqual(PartVersion.objects.get().part_id, self.part.id)
        with self.assertRaises(InputError):
            self.movement("OUT", 4, part=successor)

    def test_model_only_and_double_change_linkage(self):
        original = self.movement("IN", 8)
        intermediate = change_part(self.part, {
            "part_number": "P100", "model_number": "V2", "name": "センサ",
        })
        final = change_part(intermediate, {
            "part_number": "P200", "model_number": "V3", "name": "センサ改",
        })
        self.assertEqual(intermediate.previous_part_id, self.part.pk)
        self.assertEqual(final.previous_part_id, intermediate.pk)
        self.assertEqual(StockHistory.objects.get(pk=original.pk).model_number_snapshot, "V1")
        self.assertEqual(inventory_rows()[0]["model_number"], "V1")
        self.assertEqual(inventory_rows()[0]["quantity"], 8)
        self.assertEqual(PartVersion.objects.count(), 2)
        response = self.client.get(f"/api/parts/{final.pk}/versions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 2)

    def test_machine_section_category_reverse_lookup(self):
        machine = EquipmentMaster.objects.create(system=self.system, name="搬送装置")
        section = EquipmentSection.objects.create(equipment=machine, name="制御盤")
        category = PartCategory.objects.create(name="制御機器")
        self.part.category = category
        self.part.save()
        SystemPartPlacement.objects.create(system=self.system, part=self.part, equipment=machine, section=section)
        another = PartMaster.objects.create(
            part_number="P500", model_number="V1", name="ベアリング",
        )
        self.movement("IN", 2)
        self.movement("IN", 3, part=another)
        params = f"?equipment={machine.pk}&section={section.pk}&category={category.pk}"
        result = self.client.get("/api/parts" + params)
        self.assertEqual(result.status_code, 200)
        self.assertEqual([row["id"] for row in result.json()["items"]], [self.part.pk])
        rows = self.client.get("/api/stocks" + params).json()["items"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["part_id"], self.part.pk)
        from openpyxl import load_workbook
        excel = self.client.get("/api/export" + params)
        ws = load_workbook(io.BytesIO(b"".join(excel.streaming_content))).active
        self.assertEqual(ws.max_row, 2)
        self.assertEqual(ws["B2"].value, "P100")

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

    def test_excel_roundtrip_forks_system_stock_and_metadata(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from openpyxl import load_workbook
        from .models import StockImportBatch
        machine = EquipmentMaster.objects.create(system=self.system, name="仕分け装置", alias="ソータ")
        section = EquipmentSection.objects.create(equipment=machine, name="搬送系")
        category = PartCategory.objects.create(name="制御機器")
        self.part.category = category
        self.part.save()
        SystemPartPlacement.objects.create(system=self.system, part=self.part, equipment=machine, section=section)
        # Before successor registration this is a normal movement. Afterwards
        # the old stock must remain but no new movement may use that identifier.
        self.movement("IN", 8)
        version = change_part(self.part, {
            "part_number": "P200", "model_number": "V2", "name": "センサ新",
        })
        self.movement("IN", 3, part=version)
        self.movement("OUT", 1, part=version)
        replace_alerts(self.system, [
            {"part_id": version.id, "threshold": 3}
        ])

        download = self.client.get(f"/api/export?system={self.system.pk}")
        self.assertEqual(download.status_code, 200)
        content = b"".join(download.streaming_content)
        book = load_workbook(io.BytesIO(content))
        self.assertEqual(book["__systems"].sheet_state, "hidden")
        self.assertEqual(book["__parts"].sheet_state, "hidden")
        self.assertEqual(book["__equipment"].sheet_state, "hidden")
        self.assertEqual(book["__placements"].sheet_state, "hidden")
        self.assertEqual(book["__sections"].sheet_state, "hidden")
        self.assertEqual(book["__categories"].sheet_state, "hidden")
        self.assertEqual(book["現在庫"]["E2"].value, 8)
        book.close()

        def upload(path, **fields):
            return self.client.post(
                path, data={"file": SimpleUploadedFile(
                    "移植元.xlsx", content,
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ), **fields}
            )

        preview = upload("/api/import/preview")
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview.json()["part_count"], 2)
        self.assertEqual(preview.json()["system_count"], 1)
        self.assertEqual(preview.json()["quantity_total"], 10)
        self.assertIn("制御A", preview.json()["conflicts"])

        duplicate_name = upload("/api/import/apply")
        self.assertEqual(duplicate_name.status_code, 400)
        self.assertEqual(StockImportBatch.objects.count(), 0)

        applied = upload("/api/import/apply", system_name="制御A-複製")
        self.assertEqual(applied.status_code, 201, applied.content)
        new = SystemMaster.objects.get(name="制御A-複製")
        from .services import balance
        self.assertEqual(balance(new.pk, self.part.pk), 8)
        self.assertEqual(balance(new.pk, version.pk), 2)
        self.assertEqual(
            StockAlertSetting.objects.get(system=new, part=version).threshold, 3
        )
        self.assertEqual(PartVersion.objects.count(), 1)
        self.assertEqual(StockHistory.objects.filter(system=new).count(), 2)
        relocated = EquipmentMaster.objects.get(system=new, name="仕分け装置")
        self.assertNotEqual(machine.id, relocated.id)
        assignment = SystemPartPlacement.objects.get(system=new, part=self.part)
        self.assertEqual(assignment.equipment_id, relocated.id)
        self.assertEqual(assignment.section.name, "搬送系")

        twice = upload("/api/import/apply", system_name="制御A-複製2")
        self.assertEqual(twice.status_code, 400)
        self.assertFalse(SystemMaster.objects.filter(name="制御A-複製2").exists())
        self.assertEqual(StockImportBatch.objects.count(), 1)

    def test_excel_snapshot_allows_quantity_and_threshold_edits(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from openpyxl import load_workbook
        self.movement("IN", 2)
        book = load_workbook(io.BytesIO(
            b"".join(self.client.get(f"/api/export?system={self.system.pk}").streaming_content)
        ))
        book["現在庫"]["E2"] = 5
        book["現在庫"]["F2"] = 3
        out = io.BytesIO()
        book.save(out)
        doc = SimpleUploadedFile("数量変更.xlsx", out.getvalue())
        response = self.client.post(
            "/api/import/apply",
            data={"file": doc, "system_name": "制御A-別サイト"},
        )
        self.assertEqual(response.status_code, 201, response.content)
        system = SystemMaster.objects.get(name="制御A-別サイト")
        from .services import balance
        self.assertEqual(balance(system.pk, self.part.pk), 5)
        self.assertEqual(
            StockAlertSetting.objects.get(system=system, part=self.part).threshold, 3
        )

    def test_excel_import_rejects_modified_parts_and_negative_quantity(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from openpyxl import load_workbook
        self.movement("IN", 3)
        original = b"".join(
            self.client.get(f"/api/export?system={self.system.pk}").streaming_content
        )
        for column, value in [("E2", -2), ("B2", "FAKE-100")]:
            workbook = load_workbook(io.BytesIO(original))
            workbook["現在庫"][column] = value
            out = io.BytesIO()
            workbook.save(out)
            response = self.client.post(
                "/api/import/apply",
                data={
                    "file": SimpleUploadedFile("改ざん.xlsx", out.getvalue()),
                    "system_name": "取込テスト",
                },
            )
            self.assertEqual(response.status_code, 400, response.content)
            self.assertFalse(SystemMaster.objects.filter(name="取込テスト").exists())

    def test_excel_import_refuses_old_display_only_format(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from openpyxl import Workbook
        book = Workbook()
        ws = book.active
        ws.title = "現在庫"
        ws.append(["システム", "品番", "型式", "品名", "現在庫", "下限値", "警告"])
        data = io.BytesIO()
        book.save(data)
        resp = self.client.post(
            "/api/import/preview",
            data={"file": SimpleUploadedFile("旧形式.xlsx", data.getvalue())},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("メタデータ", resp.json()["error"])

    def test_excel_includes_zero_when_alerted(self):
        replace_alerts(self.system, [{"part_id": self.part.id, "threshold": 1}])
        response = self.client.get("/api/export")
        from openpyxl import load_workbook
        content = b"".join(response.streaming_content)
        ws = load_workbook(io.BytesIO(content)).active
        self.assertEqual(ws["E2"].value, 0)
        self.assertEqual(ws["G2"].value, "下限以下")

    def test_master_api_assigns_optional_equipment_and_category(self):
        response = self.client.post(
            "/api/equipment",
            data=json.dumps({"system_id": self.system.pk, "name": "仕分設備", "alias": "ソータ"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        equipment_id = response.json()["item"]["id"]
        section_response = self.client.post(
            "/api/equipment/sections",
            data=json.dumps({"equipment_id": equipment_id, "name": "搬送部"}),
            content_type="application/json",
        )
        self.assertEqual(section_response.status_code, 201)
        section_id = section_response.json()["item"]["id"]
        category = self.client.post(
            "/api/categories",
            data=json.dumps({"name": "機械部品"}),
            content_type="application/json",
        ).json()["item"]["id"]
        result = self.client.post(
            "/api/parts",
            data=json.dumps({
                "part_number": "P200", "model_number": "V1", "name": "ローラー",
                "system_id": self.system.pk, "equipment_id": equipment_id,
                "section_id": section_id, "category_id": category,
            }),
            content_type="application/json",
        )
        self.assertEqual(result.status_code, 201)
        self.assertEqual(result.json()["item"]["category_id"], category)
        self.assertEqual(result.json()["item"]["placements"], [{
            "system_id": self.system.pk, "equipment_id": equipment_id, "section_id": section_id,
        }])

        invalid = self.client.post(
            "/api/parts",
            data=json.dumps({
                "part_number": "P201", "model_number": "V1", "name": "ローラー",
                "section_id": section_id,
            }),
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_multiple_machines_and_sections_for_same_part_in_one_system(self):
        machine_a = EquipmentMaster.objects.create(system=self.system, name="搬送A")
        machine_b = EquipmentMaster.objects.create(system=self.system, name="搬送B")
        section_1 = EquipmentSection.objects.create(equipment=machine_a, name="駆動部")
        section_2 = EquipmentSection.objects.create(equipment=machine_a, name="センサ部")
        section_3 = EquipmentSection.objects.create(equipment=machine_b, name="駆動部")
        payload = {
            "part_number": "MULTI100", "model_number": "M1", "name": "共通センサ",
            "system_id": self.system.pk,
            "placements": [
                {"equipment_id": machine_a.pk, "section_id": section_1.pk},
                {"equipment_id": machine_a.pk, "section_id": section_2.pk},
                {"equipment_id": machine_b.pk, "section_id": section_3.pk},
                {"equipment_id": machine_b.pk, "section_id": None},
            ],
        }
        response = self.client.post("/api/parts", data=json.dumps(payload),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        part = PartMaster.objects.get(part_number="MULTI100")
        actual = set(SystemPartPlacement.objects.filter(part=part).values_list(
            "system_id", "equipment_id", "section_id"
        ))
        self.assertEqual(actual, {
            (self.system.pk, machine_a.pk, section_1.pk),
            (self.system.pk, machine_a.pk, section_2.pk),
            (self.system.pk, machine_b.pk, section_3.pk),
            (self.system.pk, machine_b.pk, None),
        })
        self.assertEqual(len(response.json()["item"]["placements"]), 4)
        for equipment, section in [
            (machine_a, section_1), (machine_a, section_2),
            (machine_b, section_3),
        ]:
            filtered = self.client.get(
                f"/api/parts?system={self.system.pk}&equipment={equipment.pk}&section={section.pk}"
            )
            self.assertIn(part.pk, [p["id"] for p in filtered.json()["items"]])
        # Selecting one machine must not duplicate the part in the API result.
        by_machine = self.client.get(f"/api/parts?equipment={machine_a.pk}")
        self.assertEqual(sum(p["id"] == part.pk for p in by_machine.json()["items"]), 1)

    def test_multi_placements_edit_replace_per_system_and_version_copies_all(self):
        machine = EquipmentMaster.objects.create(system=self.system, name="CV")
        sections = [
            EquipmentSection.objects.create(equipment=machine, name=name)
            for name in ("ローラー", "駆動", "光電")
        ]
        other_machine = EquipmentMaster.objects.create(system=self.other, name="CV")
        SystemPartPlacement.objects.create(
            system=self.other, part=self.part, equipment=other_machine
        )
        payload = {
            "part_number": self.part.part_number, "model_number": self.part.model_number,
            "name": self.part.name, "system_id": self.system.pk,
            "placements": [
                {"equipment_id": machine.pk, "section_id": sections[0].pk},
                {"equipment_id": machine.pk, "section_id": sections[1].pk},
            ],
        }
        change_part(self.part, payload)
        self.assertEqual(self.part.placements.count(), 3)
        change_part(self.part, {
            **payload,
            "placements": [{"equipment_id": machine.pk, "section_id": sections[2].pk}],
        })
        self.assertEqual(self.part.placements.count(), 2)
        self.assertTrue(self.part.placements.filter(system=self.other, equipment=other_machine).exists())
        successor = change_part(self.part, {
            **payload,
            "part_number": "MULTI200", "model_number": "V2",
            "placements": [
                {"equipment_id": machine.pk, "section_id": sections[0].pk},
                {"equipment_id": machine.pk, "section_id": sections[1].pk},
                {"equipment_id": machine.pk, "section_id": sections[2].pk},
            ],
        })
        self.assertEqual(successor.placements.count(), 4)
        self.assertTrue(self.part.placements.filter(
            system=self.system, section=sections[2]
        ).exists())
        self.assertEqual(PartVersion.objects.filter(part=self.part).count(), 1)

    def test_multi_assignment_rejects_duplicates_and_foreign_sections_atomically(self):
        machine = EquipmentMaster.objects.create(system=self.system, name="検査機")
        other_machine = EquipmentMaster.objects.create(system=self.other, name="検査機")
        section = EquipmentSection.objects.create(equipment=machine, name="制御部")
        base = {
            "part_number": "ERROR100", "model_number": "V1", "name": "不正テスト",
            "system_id": self.system.pk,
        }
        for entries in [
            [{"equipment_id": machine.pk, "section_id": section.pk}] * 2,
            [{"equipment_id": machine.pk}] * 2,
            [{"equipment_id": other_machine.pk}],
            [{"equipment_id": other_machine.pk, "section_id": section.pk}],
            [{"equipment_id": machine.pk, "section_id": -1}],
        ]:
            response = self.client.post(
                "/api/parts", content_type="application/json",
                data=json.dumps({**base, "placements": entries}),
            )
            self.assertEqual(response.status_code, 400, response.content)
            self.assertFalse(PartMaster.objects.filter(part_number="ERROR100").exists())

    def test_excel_fork_preserves_multi_machine_placements_and_legacy_v2(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from openpyxl import load_workbook
        machine = EquipmentMaster.objects.create(system=self.system, name="分岐機")
        sections = [EquipmentSection.objects.create(equipment=machine, name=name)
                    for name in ("入口", "出口")]
        for sec in sections:
            SystemPartPlacement.objects.create(
                system=self.system, part=self.part, equipment=machine, section=sec
            )
        self.movement("IN", 7)
        stream = b"".join(self.client.get(
            f"/api/export?system={self.system.pk}"
        ).streaming_content)
        book = load_workbook(io.BytesIO(stream))
        self.assertEqual(book["__manifest"]["B2"].value, "SPARE_PARTS_SNAPSHOT_V3")
        self.assertEqual(book["__placements"].max_row, 3)
        for label, content in (("複製V3", stream), ("複製V2", None)):
            if content is None:
                book["__manifest"]["B2"] = "SPARE_PARTS_SNAPSHOT_V2"
                dest = io.BytesIO()
                book.save(dest)
                content = dest.getvalue()
            result = self.client.post("/api/import/apply", data={
                "file": SimpleUploadedFile("部品移植.xlsx", content), "system_name": label,
            })
            self.assertEqual(result.status_code, 201, result.content)
            new = SystemMaster.objects.get(name=label)
            target = EquipmentMaster.objects.get(system=new, name="分岐機")
            self.assertEqual(set(SystemPartPlacement.objects.filter(
                system=new, part=self.part
            ).values_list("equipment_id", "section__name")), {
                (target.pk, "入口"), (target.pk, "出口"),
            })
            from .services import balance
            self.assertEqual(balance(new.pk, self.part.pk), 7)

    def test_equipment_is_system_scoped_and_parts_shared(self):
        a = EquipmentMaster.objects.create(system=self.system, name="仕分設備")
        b = EquipmentMaster.objects.create(system=self.other, name="仕分設備")
        self.assertNotEqual(a.pk, b.pk)
        SystemPartPlacement.objects.create(system=self.system, part=self.part, equipment=a)
        SystemPartPlacement.objects.create(system=self.other, part=self.part, equipment=b)
        self.assertEqual(SystemPartPlacement.objects.filter(part=self.part).count(), 2)
        self.assertEqual([x["id"] for x in self.client.get(
            "/api/parts?system=" + str(self.other.id) + "&equipment=" + str(b.id)
        ).json()["items"]], [self.part.pk])
        with self.assertRaises(InputError):
            create_part({
                "part_number": "BAD-1", "model_number": "1", "name": "誤割当",
                "system_id": self.system.pk, "equipment_id": b.pk,
            })
        self.assertFalse(PartMaster.objects.filter(part_number="BAD-1").exists())

    def test_stock_summary_last_movement_order_and_history_ascending(self):
        first = self.movement("IN", 1)
        second = self.movement("IN", 1, part=PartMaster.objects.create(
            part_number="P200", model_number="V1", name="新しい部品",
        ))
        rows = inventory_rows()
        self.assertEqual(rows[0]["part_number"], "P200")
        self.assertGreaterEqual(rows[0]["last_updated"], rows[1]["last_updated"])
        history_ids = [v["id"] for v in self.client.get("/api/history").json()["items"]]
        self.assertEqual(history_ids, [first.id, second.id])
        systems = [v["id"] for v in self.client.get("/api/systems").json()["items"]]
        self.assertEqual(systems, sorted(systems))

    def test_superseded_part_can_be_issued_not_replenished_or_edited(self):
        original = self.movement("IN", 4)
        successor = change_part(self.part, {
            "part_number": "P200", "model_number": "V2", "name": "現行センサ",
        })
        self.assertEqual(PartMaster.objects.count(), 2)
        current_ids = [row["id"] for row in self.client.get(
            "/api/parts?current_only=1"
        ).json()["items"]]
        self.assertEqual(current_ids, [successor.pk])
        self.assertEqual(len(self.client.get("/api/parts").json()["items"]), 2)
        rejected = self.client.post(
            "/api/history", content_type="application/json",
            data=json.dumps({
                "system_id": self.system.pk, "part_id": self.part.pk,
                "direction": "IN", "quantity": 1, "operator": "担当者",
            }),
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("補充できません", rejected.json()["error"])
        issued = self.movement("OUT", 2)
        self.assertEqual(issued.part_id, self.part.pk)
        old_row = next(row for row in inventory_rows() if row["part_number"] == "P100")
        self.assertEqual(old_row["quantity"], 2)
        with self.assertRaises(InputError):
            self.movement("OUT", 3)
        with self.assertRaises(InputError):
            change_part(self.part, {
                "part_number": "P100", "model_number": "V1", "name": "誤編集",
            })
        self.part.refresh_from_db()
        self.assertEqual(self.part.name, "センサ")
        self.movement("IN", 3, part=successor)
        self.assertEqual(
            {r["part_number"]: r["quantity"] for r in inventory_rows()},
            {"P100": 2, "P200": 3},
        )
        correct_movement(original.id, {
            "direction": "IN", "quantity": 3, "operator": "担当者",
            "note": "旧レコード数量訂正",
        })
        old_row = next(row for row in inventory_rows() if row["part_number"] == "P100")
        self.assertEqual(old_row["quantity"], 1)
        self.assertEqual(StockHistory.objects.filter(part=self.part).count(), 4)

    def test_superseded_part_issue_via_api_succeeds_until_stock_zero(self):
        self.movement("IN", 2)
        change_part(self.part, {
            "part_number": "P100", "model_number": "V2", "name": "現行センサ",
        })
        data = {"system_id": self.system.pk, "part_id": self.part.pk,
                "operator": "担当者", "direction": "OUT"}
        ok = self.client.post("/api/history", content_type="application/json",
                              data=json.dumps({**data, "quantity": 2}))
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertFalse(any(
            row["part_id"] == self.part.pk
            for row in inventory_rows(self.system.pk)
        ))
        too_many = self.client.post("/api/history", content_type="application/json",
                                    data=json.dumps({**data, "quantity": 1}))
        self.assertEqual(too_many.status_code, 400)
        self.assertIn("在庫が不足", too_many.json()["error"])
        in_old = self.client.post("/api/history", content_type="application/json",
                                  data=json.dumps({**data, "direction": "IN", "quantity": 1}))
        self.assertEqual(in_old.status_code, 400)

    def test_machine_copy_duplicates_sections_but_not_placement_or_stock(self):
        origin = EquipmentMaster.objects.create(system=self.system, name="搬送機", alias="CV")
        EquipmentSection.objects.create(equipment=origin, name="駆動部")
        EquipmentSection.objects.create(equipment=origin, name="センサ部")
        SystemPartPlacement.objects.create(system=self.system, part=self.part, equipment=origin)
        self.movement("IN", 6)
        response = self.client.post(
            f"/api/equipment/{origin.pk}/copy",
            content_type="application/json",
            data=json.dumps({"system_id": self.other.pk, "name": "搬送機", "alias": "CV"}),
        )
        self.assertEqual(response.status_code, 201, response.content)
        copied = EquipmentMaster.objects.get(pk=response.json()["item"]["id"])
        self.assertEqual(copied.system_id, self.other.pk)
        self.assertEqual(copied.alias, "CV")
        self.assertEqual(
            list(copied.sections.order_by("name").values_list("name", flat=True)),
            ["センサ部", "駆動部"],
        )
        self.assertFalse(SystemPartPlacement.objects.filter(system=self.other).exists())
        self.assertFalse(StockHistory.objects.filter(system=self.other).exists())
        # Duplicate names must roll back both machine and its sections.
        again = self.client.post(
            f"/api/equipment/{origin.pk}/copy",
            content_type="application/json",
            data=json.dumps({"system_id": self.other.pk, "name": "搬送機", "alias": "CV"}),
        )
        self.assertEqual(again.status_code, 409)
        self.assertEqual(EquipmentSection.objects.count(), 4)

    def test_part_copy_is_not_a_successor_and_can_reuse_placements(self):
        machine = EquipmentMaster.objects.create(system=self.system, name="CV")
        section = EquipmentSection.objects.create(equipment=machine, name="駆動部")
        category = PartCategory.objects.create(name="機械部品")
        self.part.category = category
        self.part.save()
        SystemPartPlacement.objects.create(
            system=self.system, part=self.part, equipment=machine, section=section,
        )
        response = self.client.post(
            "/api/parts",
            content_type="application/json",
            data=json.dumps({
                "part_number": "P101", "model_number": "V1", "name": self.part.name,
                "system_id": self.system.pk, "equipment_id": machine.pk,
                "section_id": section.pk, "category_id": category.pk,
            }),
        )
        self.assertEqual(response.status_code, 201, response.content)
        copied = PartMaster.objects.get(pk=response.json()["item"]["id"])
        self.assertIsNone(copied.previous_part_id)
        self.assertEqual(copied.category_id, category.pk)
        self.assertEqual(SystemPartPlacement.objects.get(part=copied).section_id, section.pk)
        self.assertEqual(StockHistory.objects.count(), 0)

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
