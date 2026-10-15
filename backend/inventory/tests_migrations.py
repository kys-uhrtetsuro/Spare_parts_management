"""Compatibility test for databases created before successor parts were separate."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class PreviousIdentifierMigrationTests(TransactionTestCase):
    migrate_from = ("inventory", "0002_remove_stockhistory_company")
    migrate_to = ("inventory", "0003_equipment_and_lineage")

    def test_old_and_new_identifier_history_is_split_without_rewriting_snapshots(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        legacy = executor.loader.project_state([self.migrate_from]).apps
        System = legacy.get_model("inventory", "SystemMaster")
        Part = legacy.get_model("inventory", "PartMaster")
        Version = legacy.get_model("inventory", "PartVersion")
        History = legacy.get_model("inventory", "StockHistory")

        system = System.objects.create(name="既存システム")
        overwritten = Part.objects.create(
            part_number="NEW-200", model_number="V2", name="交換用センサ",
        )
        Version.objects.create(
            part=overwritten, old_part_number="OLD-100",
            old_model_number="V1", new_part_number="NEW-200",
            new_model_number="V2",
        )
        History.objects.create(
            system=system, part=overwritten, direction="IN", quantity=5,
            operator="担当者", part_number_snapshot="OLD-100",
            model_number_snapshot="V1",
        )
        History.objects.create(
            system=system, part=overwritten, direction="IN", quantity=2,
            operator="担当者", part_number_snapshot="NEW-200",
            model_number_snapshot="V2",
        )
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        migrated = executor.loader.project_state([self.migrate_to]).apps
        NewPart = migrated.get_model("inventory", "PartMaster")
        NewHistory = migrated.get_model("inventory", "StockHistory")
        old = NewPart.objects.get(part_number="OLD-100", model_number="V1")
        new = NewPart.objects.get(part_number="NEW-200", model_number="V2")
        self.assertEqual(new.previous_part_id, old.pk)
        self.assertEqual(
            list(NewHistory.objects.filter(part_id=old.id).values_list(
                "part_number_snapshot", "quantity",
            )),
            [("OLD-100", 5)],
        )
        self.assertEqual(
            list(NewHistory.objects.filter(part_id=new.id).values_list(
                "part_number_snapshot", "quantity",
            )),
            [("NEW-200", 2)],
        )
