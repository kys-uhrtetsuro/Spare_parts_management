"""Inventory calculations and write operations. The ledger is the source of truth."""
from collections import defaultdict
from threading import RLock

from django.db import IntegrityError, transaction
from django.db.models import Case, F, IntegerField, Sum, When

from .models import EquipmentMaster, EquipmentSection, PartCategory, PartMaster, PartVersion, StockAlertSetting, StockHistory, SystemMaster

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
            "alert": threshold is not None and amount <= threshold,
        })
    return sorted(result, key=lambda r: (r["system"], r["part_number"], r["model_number"]))


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
        if direction == StockHistory.OUT and balance(system.id, part.id) < quantity:
            raise InputError("在庫が不足しています。マイナス在庫になる登録はできません")
        obj = StockHistory.objects.create(
            system=system, part=part, direction=direction, quantity=quantity,
            operator=operator, note=note,
            part_number_snapshot=part.part_number, model_number_snapshot=part.model_number,
        )
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
    return reverse, revised


def optional_fk(model, value, label):
    if value in (None, ""):
        return None
    pk = positive_int(value, label)
    if not model.objects.filter(pk=pk).exists():
        raise InputError(f"{label}が存在しません")
    return pk


def part_assignments(data, original=None):
    # Existing assignments remain intact if a legacy caller omits the keys.
    equipment_id = optional_fk(
        EquipmentMaster,
        data.get("equipment_id", original.equipment_id if original else None), "機器"
    )
    section_id = optional_fk(
        EquipmentSection,
        data.get("section_id", original.section_id if original else None), "部位"
    )
    category_id = optional_fk(
        PartCategory,
        data.get("category_id", original.category_id if original else None), "分類"
    )
    if section_id is not None and (
        equipment_id is None or not EquipmentSection.objects.filter(
            pk=section_id, equipment_id=equipment_id
        ).exists()
    ):
        raise InputError("部位と機器の組み合わせが一致していません")
    return {"equipment_id": equipment_id, "section_id": section_id, "category_id": category_id}


def change_part(part, data):
    new_number = text_field(data.get("part_number"), "品番", 160)
    new_model = text_field(data.get("model_number"), "型式", 160)
    new_name = text_field(data.get("name"), "品名", 250)
    attributes = part_assignments(data, part)
    with WRITE_LOCK, transaction.atomic():
        if (part.part_number, part.model_number) == (new_number, new_model):
            # Name/assignment edits do not change the identifier or stock history.
            part.name = new_name
            for field, value in attributes.items():
                setattr(part, field, value)
            part.save()
            return part

        # Upgrading an identifier creates a separate PartMaster. Never mutate the
        # identifier attached to stock already registered under the old version.
        successor = PartMaster.objects.create(
            part_number=new_number, model_number=new_model, name=new_name,
            previous_part=part, **attributes,
        )
        PartVersion.objects.create(
            part=part, old_part_number=part.part_number, old_model_number=part.model_number,
            new_part_number=successor.part_number, new_model_number=successor.model_number,
        )
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
        StockAlertSetting.objects.filter(system=system).exclude(part_id__in=parsed).delete()
        for pid, value in parsed.items():
            StockAlertSetting.objects.update_or_create(
                system=system, part_id=pid, defaults={"threshold": value}
            )
    return len(parsed)
