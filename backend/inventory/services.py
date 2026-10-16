"""Inventory calculations and write operations. The ledger is the source of truth."""
from collections import defaultdict
from datetime import datetime
from threading import RLock

from django.db import IntegrityError, transaction
from django.db.models import Case, F, IntegerField, Max, Sum, When

from .models import EquipmentMaster, EquipmentSection, PartCategory, PartMaster, PartVersion, StockAlertSetting, StockHistory, SystemMaster, SystemPartPlacement

# This GUI operates one Django server per database. Serialize writes within the process.
WRITE_LOCK = RLock()


class InputError(Exception):
    pass


def positive_int(value, label="数量"):
    if isinstance(value, bool):
        raise InputError(f"{label}は1以上の整数を指定してください")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise InputError(f"{label}は1以上の整数を指定してください") from None
    if str(value).strip() != str(result) or result < 1 or result > 2_147_483_647:
        raise InputError(f"{label}は1以上の整数を指定してください")
    return result


def text_field(value, label, maximum, required=True):
    if not isinstance(value, str):
        raise InputError(f"{label}が不正です")
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        raise InputError(f"{label}は1〜{maximum}文字で入力してください")
    return value


def find_system(system_id):
    try:
        return SystemMaster.objects.get(pk=positive_int(system_id, "システムID"))
    except SystemMaster.DoesNotExist:
        raise InputError("指定システムが存在しません") from None


def find_part(part_id):
    try:
        return PartMaster.objects.get(pk=positive_int(part_id, "部品ID"))
    except PartMaster.DoesNotExist:
        raise InputError("指定部品が存在しません") from None


def balance(system_id, part_id):
    total = StockHistory.objects.filter(system_id=system_id, part_id=part_id).aggregate(
        value=Sum(Case(
            When(direction=StockHistory.IN, then=F("quantity")),
            default=-F("quantity"), output_field=IntegerField(),
        ))
    )["value"]
    return total or 0


def balances():
    result = {}
    qs = StockHistory.objects.values("system_id", "part_id").annotate(
        value=Sum(Case(
            When(direction=StockHistory.IN, then=F("quantity")),
            default=-F("quantity"), output_field=IntegerField(),
        ))
    )
    for row in qs:
        result[(row["system_id"], row["part_id"])] = row["value"] or 0
    return result


def inventory_rows(system_id=None, show_all=False):
    stock = balances()
    thresholds = {
        (v["system_id"], v["part_id"]): v["threshold"]
        for v in StockAlertSetting.objects.values("system_id", "part_id", "threshold")
    }
    parts = PartMaster.objects.in_bulk()
    systems = SystemMaster.objects.in_bulk()
    keys = set(stock) | set(thresholds)
    if show_all:
        keys |= {(s, p) for s in systems for p in parts}
    recent = {
        (r["system_id"], r["part_id"]): r["updated"]
        for r in StockHistory.objects.values("system_id", "part_id").annotate(
            updated=Max("created_at")
        )
    }
    result = []
    for sid, pid in keys:
        if system_id is not None and sid != system_id:
            continue
        part = parts.get(pid)
        system = systems.get(sid)
        if not part or not system:
            continue
        amount = stock.get((sid, pid), 0)
        threshold = thresholds.get((sid, pid))
        if not show_all and amount < 1 and threshold is None:
            continue
        result.append({
            "system_id": sid, "system": system.name, "part_id": pid,
            "part_number": part.part_number, "model_number": part.model_number,
            "name": part.name, "quantity": amount, "threshold": threshold,
            "last_updated": recent.get((sid, pid)).isoformat() if recent.get((sid, pid)) else None,
            "alert": threshold is not None and amount <= threshold,
        })
    # Newest movement first; monitored parts with no movement come last.
    return sorted(result, key=lambda r: (
        r["last_updated"] is None,
        -datetime.fromisoformat(r["last_updated"]).timestamp() if r["last_updated"] else 0,
        r["system_id"], r["part_id"]
    ))



def reconcile_alert_lineage(system_id):
    """Keep one meaningful alert per revision chain of each system.

    A monitored obsolete part remains monitored while its stock is positive.
    Once a newer version receives stock, move the existing threshold to that
    revision without creating duplicate alerts. If the obsolete stock runs out
    before its successor is stocked, drop the obsolete setting. An explicitly
    configured current-part alert is never overwritten.
    """
    alerts = {
        row.part_id: row for row in StockAlertSetting.objects.filter(system_id=system_id)
    }
    if not alerts:
        return
    parents = dict(PartMaster.objects.values_list("id", "previous_part_id"))
    children = defaultdict(list)
    for part_id, parent_id in parents.items():
        if parent_id is not None:
            children[parent_id].append(part_id)

    def descendants(part_id):
        result = []
        pending = [(part_id, 0)]
        seen = {part_id}
        while pending:
            current, depth = pending.pop()
            for child in children.get(current, ()):
                if child in seen:
                    continue
                seen.add(child)
                result.append((depth + 1, child))
                pending.append((child, depth + 1))
        return sorted(result, reverse=True)

    stocks = {
        row["part_id"]: row["total"] or 0
        for row in StockHistory.objects.filter(system_id=system_id)
        .values("part_id").annotate(
            total=Sum(Case(
                When(direction=StockHistory.IN, then=F("quantity")),
                default=-F("quantity"), output_field=IntegerField(),
            ))
        )
    }
    # Shallowest first: transfers to a terminal revision in one pass.
    to_remove = set()
    for old_id, alert in list(alerts.items()):
        if old_id in to_remove:
            continue
        newer = descendants(old_id)
        if not newer:
            continue
        # If a successor is already being monitored, its own threshold wins.
        existing_newer = next((pid for _, pid in newer
                               if pid in alerts and pid not in to_remove), None)
        stocked_newer = next((pid for _, pid in newer if stocks.get(pid, 0) > 0), None)
        target_id = existing_newer or stocked_newer
        if target_id:
            if target_id not in alerts:
                new_alert = StockAlertSetting.objects.create(
                    system_id=system_id, part_id=target_id, threshold=alert.threshold
                )
                alerts[target_id] = new_alert
            to_remove.add(old_id)
        elif stocks.get(old_id, 0) <= 0:
            to_remove.add(old_id)
    if to_remove:
        StockAlertSetting.objects.filter(
            system_id=system_id, part_id__in=to_remove
        ).delete()


def create_movement(data):
    system = find_system(data.get("system_id"))
    part = find_part(data.get("part_id"))
    direction = data.get("direction")
    if direction not in (StockHistory.IN, StockHistory.OUT):
        raise InputError("区分は補充または使用を指定してください")
    quantity = positive_int(data.get("quantity"))
    operator = text_field(data.get("operator"), "登録者名", 160)
    note = text_field(data.get("note", ""), "備考", 400, required=False)
    with WRITE_LOCK, transaction.atomic():
        # Do not allow registering new movements under a superseded identifier.
        # Existing ledger corrections remain available for audit.
        if direction == StockHistory.IN and PartMaster.objects.filter(previous_part_id=part.id).exists():
            raise InputError("後継品のある旧品番・旧型式には補充できません。現行品を選択してください")
        if direction == StockHistory.OUT and balance(system.id, part.id) < quantity:
            raise InputError("在庫が不足しています。マイナス在庫になる登録はできません")
        obj = StockHistory.objects.create(
            system=system, part=part, direction=direction, quantity=quantity,
            operator=operator, note=note,
            part_number_snapshot=part.part_number, model_number_snapshot=part.model_number,
        )
        reconcile_alert_lineage(system.pk)
    return obj


def correct_movement(history_id, data):
    try:
        original = StockHistory.objects.select_related("system", "part").get(
            pk=positive_int(history_id, "履歴ID")
        )
    except StockHistory.DoesNotExist:
        raise InputError("対象履歴がありません") from None
    if original.reversal_of_id is not None:
        raise InputError("取消履歴は訂正できません")
    direction = data.get("direction")
    if direction not in (StockHistory.IN, StockHistory.OUT):
        raise InputError("訂正区分が不正です")
    quantity = positive_int(data.get("quantity"))
    operator = text_field(data.get("operator"), "登録者名", 160)
    note = text_field(data.get("note", ""), "訂正理由", 400)
    with WRITE_LOCK, transaction.atomic():
        if StockHistory.objects.filter(reversal_of_id=original.id).exists():
            raise InputError("この履歴は既に訂正済みです")
        current = balance(original.system_id, original.part_id)
        old_delta = original.signed_quantity()
        new_delta = quantity if direction == StockHistory.IN else -quantity
        if current - old_delta + new_delta < 0:
            raise InputError("訂正後にマイナス在庫になるため登録できません")
        reverse = StockHistory.objects.create(
            system=original.system, part=original.part,
            direction=StockHistory.OUT if original.direction == StockHistory.IN else StockHistory.IN,
            quantity=original.quantity, operator=operator,
            note=f"履歴#{original.pk}取消: {note}"[:400],
            part_number_snapshot=original.part_number_snapshot,
            model_number_snapshot=original.model_number_snapshot,
            reversal_of=original,
        )
        revised = StockHistory.objects.create(
            system=original.system, part=original.part,
            direction=direction, quantity=quantity, operator=operator,
            note=f"履歴#{original.pk}訂正: {note}"[:400],
            part_number_snapshot=original.part.part_number,
            model_number_snapshot=original.part.model_number,
        )
        reconcile_alert_lineage(original.system_id)
    return reverse, revised


def optional_fk(model, value, label):
    if value in (None, ""):
        return None
    pk = positive_int(value, label)
    if not model.objects.filter(pk=pk).exists():
        raise InputError(f"{label}が存在しません")
    return pk


def part_assignments(data, original=None):
    """Validate optional assignments to multiple equipment/sections in one system.

    Backwards-compatible with existing clients that provide equipment_id and
    section_id instead of the placements list.
    """
    category_id = optional_fk(
        PartCategory, data.get("category_id", original.category_id if original else None),
        "分類",
    )
    system_id = optional_fk(SystemMaster, data.get("system_id"), "システム")
    if "placements" in data:
        entries = data["placements"]
        if not isinstance(entries, list):
            raise InputError("機器・部位の割当一覧が不正です")
    else:
        equipment_id = data.get("equipment_id")
        section_id = data.get("section_id")
        entries = ([{"equipment_id": equipment_id, "section_id": section_id}]
                   if equipment_id not in (None, "") or section_id not in (None, "") else [])

    if len(entries) > 1000:
        raise InputError("機器・部位の割当件数が多すぎます")
    parsed = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise InputError("機器・部位の割当が不正です")
        eid = optional_fk(EquipmentMaster, entry.get("equipment_id"), "機器")
        sid = optional_fk(EquipmentSection, entry.get("section_id"), "部位")
        if eid is None:
            raise InputError("機器・部位の割当には機器を選択してください")
        if system_id is None or not EquipmentMaster.objects.filter(
            pk=eid, system_id=system_id,
        ).exists():
            raise InputError("機器は選択したシステムに属している必要があります")
        if sid is not None and not EquipmentSection.objects.filter(
            pk=sid, equipment_id=eid,
        ).exists():
            raise InputError("部位と機器の組み合わせが一致していません")
        key = (eid, sid)
        if key in seen:
            raise InputError("同じ機器・部位の組み合わせを重複登録できません")
        seen.add(key)
        parsed.append(key)
    return category_id, system_id, parsed


def save_placements(part, system_id, assignments):
    """Replace assignments for one system; keep those from other systems."""
    if system_id is None:
        return
    SystemPartPlacement.objects.filter(part=part, system_id=system_id).delete()
    SystemPartPlacement.objects.bulk_create([
        SystemPartPlacement(
            part=part, system_id=system_id,
            equipment_id=equipment_id, section_id=section_id,
        ) for equipment_id, section_id in assignments
    ])


def create_part(data):
    number = text_field(data.get("part_number"), "品番", 160)
    model = text_field(data.get("model_number", ""), "型式", 160, required=False)
    name = text_field(data.get("name"), "品名", 250)
    category_id, system_id, assignments = part_assignments(data)
    with WRITE_LOCK, transaction.atomic():
        result = PartMaster.objects.create(
            part_number=number, model_number=model, name=name, category_id=category_id
        )
        save_placements(result, system_id, assignments)
    return result


def change_part(part, data):
    new_number = text_field(data.get("part_number"), "品番", 160)
    new_model = text_field(data.get("model_number", ""), "型式", 160, required=False)
    new_name = text_field(data.get("name"), "品名", 250)
    category_id, system_id, assignments = part_assignments(data, part)
    with WRITE_LOCK, transaction.atomic():
        if PartMaster.objects.filter(previous_part_id=part.pk).exists():
            raise InputError("後継登録済みの旧品番・旧型式は編集できません")
        if (part.part_number, part.model_number) == (new_number, new_model):
            part.name = new_name
            part.category_id = category_id
            part.save()
            if system_id is not None:
                save_placements(part, system_id, assignments)
            return part

        successor = PartMaster.objects.create(
            part_number=new_number, model_number=new_model, name=new_name,
            category_id=category_id, previous_part=part,
        )
        SystemPartPlacement.objects.bulk_create([
            SystemPartPlacement(
                system_id=p.system_id, part=successor, equipment_id=p.equipment_id,
                section_id=p.section_id,
            ) for p in SystemPartPlacement.objects.filter(part=part)
        ])
        if system_id is not None:
            save_placements(successor, system_id, assignments)
        PartVersion.objects.create(
            part=part, old_part_number=part.part_number, old_model_number=part.model_number,
            new_part_number=successor.part_number, new_model_number=successor.model_number,
        )
        for alert_system_id in StockAlertSetting.objects.filter(part=part).values_list(
            "system_id", flat=True
        ).distinct():
            reconcile_alert_lineage(alert_system_id)
        return successor


def replace_alerts(system, items):
    if not isinstance(items, list):
        raise InputError("設定対象が不正です")
    parsed = {}
    for item in items:
        if not isinstance(item, dict):
            raise InputError("設定内容が不正です")
        pid = positive_int(item.get("part_id"), "部品ID")
        threshold = positive_int(item.get("threshold"), "下限値")
        if pid in parsed:
            raise InputError("同一部品を重複登録できません")
        parsed[pid] = threshold
    if len(PartMaster.objects.filter(pk__in=parsed)) != len(parsed):
        raise InputError("存在しない部品が含まれます")
    with WRITE_LOCK, transaction.atomic():
        existing = dict(StockAlertSetting.objects.filter(system=system).values_list(
            "part_id", "threshold"
        ))
        obsolete = set(PartMaster.objects.filter(
            pk__in=parsed, successors__isnull=False
        ).values_list("pk", flat=True))
        for pid in obsolete:
            if existing.get(pid) != parsed[pid]:
                raise InputError("後継登録済みの部品に下限アラートを新規設定・変更できません")
        StockAlertSetting.objects.filter(system=system).exclude(part_id__in=parsed).delete()
        for pid, value in parsed.items():
            StockAlertSetting.objects.update_or_create(
                system=system, part_id=pid, defaults={"threshold": value}
            )
        reconcile_alert_lineage(system.pk)
    return StockAlertSetting.objects.filter(system=system).count()
