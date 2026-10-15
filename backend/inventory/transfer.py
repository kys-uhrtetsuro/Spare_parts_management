"""Portable, system-scoped Excel snapshot export and safe import.

The visible sheet is editable. Master metadata is stored in hidden worksheets.
An import creates opening stock movements; it intentionally does not copy
historical movements from the source database.
"""
import hashlib
import io
import zipfile
from collections import defaultdict
from datetime import datetime

import pandas as pd
from django.db import transaction
from django.db.models import Q
from openpyxl import load_workbook

from .models import (
    EquipmentMaster, EquipmentSection, PartCategory, PartMaster, PartVersion,
    StockAlertSetting, StockHistory, StockImportBatch, SystemMaster,
)
from .services import InputError, WRITE_LOCK, balances, text_field

FORMAT = "SPARE_PARTS_SNAPSHOT_V1"
HEADERS = ("システム", "品番", "型式", "品名", "現在庫", "下限値", "警告")
SCHEMAS = {
    "__manifest": ("key", "value"),
    "__systems": ("id", "name"),
    "__equipment": ("id", "name", "alias"),
    "__sections": ("id", "equipment_id", "name"),
    "__categories": ("id", "name"),
    "__parts": ("id", "part_number", "model_number", "name",
                "previous_part_id", "equipment_id", "section_id", "category_id"),
    "__stocks": ("system_id", "part_id", "quantity"),
    "__alerts": ("system_id", "part_id", "threshold"),
}
MAX_XLSX_BYTES = 10 * 1024 * 1024
MAX_INFLATED_BYTES = 40 * 1024 * 1024
MAX_ROWS = 10000


def safe_excel(value):
    """Prevent spreadsheet formula execution in the public-facing sheet."""
    return "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value


def nonnegative(value, label, *, allow_zero=True):
    if isinstance(value, bool) or value is None:
        raise InputError(f"{label}には整数を入力してください")
    if isinstance(value, float):
        if not value.is_integer():
            raise InputError(f"{label}には整数を入力してください")
        value = int(value)
    if isinstance(value, str):
        if not value.strip().isdigit():
            raise InputError(f"{label}には整数を入力してください")
        value = int(value.strip())
    if not isinstance(value, int) or value < (0 if allow_zero else 1) or value > 2147483647:
        raise InputError(f"{label}には{'0' if allow_zero else '1'}以上の整数を入力してください")
    return value


def _select_ids(system_ids, filters):
    """Part masters actively referenced by selected systems, plus their lineage."""
    used = set(StockHistory.objects.filter(system_id__in=system_ids).values_list("part_id", flat=True))
    used.update(StockAlertSetting.objects.filter(system_id__in=system_ids).values_list("part_id", flat=True))
    if filters:
        allowed = set(PartMaster.objects.filter(**filters).values_list("id", flat=True))
        used.intersection_update(allowed)
    all_parts = dict(PartMaster.objects.values_list("id", "previous_part_id"))
    # Include ancestors and successors so the copied system knows its upgrade chains.
    selected = set(used)
    for _ in range(len(all_parts) + 1):
        expanded = selected.copy()
        for pid in selected:
            parent = all_parts.get(pid)
            if parent:
                expanded.add(parent)
        for pid, parent in all_parts.items():
            if parent in selected:
                expanded.add(pid)
        if expanded == selected:
            break
        selected = expanded
    return selected


def write_snapshot(system_id=None, filters=None):
    filters = filters or {}
    systems = list(SystemMaster.objects.filter(pk=system_id) if system_id else SystemMaster.objects.all())
    system_ids = [obj.pk for obj in systems]
    part_ids = _select_ids(system_ids, filters)
    parts = list(PartMaster.objects.filter(pk__in=part_ids).order_by("id"))
    equipment_ids = {part.equipment_id for part in parts if part.equipment_id}
    section_ids = {part.section_id for part in parts if part.section_id}
    category_ids = {part.category_id for part in parts if part.category_id}
    equipment_ids.update(
        EquipmentSection.objects.filter(pk__in=section_ids).values_list("equipment_id", flat=True)
    )
    equipment = list(EquipmentMaster.objects.filter(pk__in=equipment_ids).order_by("pk"))
    sections = list(EquipmentSection.objects.filter(pk__in=section_ids).order_by("pk"))
    categories = list(PartCategory.objects.filter(pk__in=category_ids).order_by("pk"))
    stock = balances()
    alerts = list(StockAlertSetting.objects.filter(
        system_id__in=system_ids, part_id__in=part_ids
    ).order_by("system_id", "part_id"))
    threshold_map = {(a.system_id, a.part_id): a.threshold for a in alerts}
    part_map = {p.id: p for p in parts}
    sys_map = {s.id: s.name for s in systems}
    # Export visible rows only with stock>0 or an active alert; hidden sheets carry
    # all referenced masters including old zero-stock identifiers.
    visible = []
    hidden_stocks = []
    for sid in sorted(system_ids):
        for pid in sorted(part_ids):
            qty = stock.get((sid, pid), 0)
            threshold = threshold_map.get((sid, pid))
            hidden_stocks.append((sid, pid, qty))
            if qty > 0 or threshold is not None:
                p = part_map[pid]
                visible.append({
                    "システム": safe_excel(sys_map[sid]),
                    "品番": safe_excel(p.part_number),
                    "型式": safe_excel(p.model_number),
                    "品名": safe_excel(p.name),
                    "現在庫": qty,
                    "下限値": threshold,
                    "警告": "下限以下" if threshold is not None and qty <= threshold else "",
                })

    # Pandas owns the human-facing table; openpyxl owns relational metadata.
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(visible, columns=HEADERS).to_excel(
            writer, sheet_name="現在庫", index=False
        )
        sheets = {
            "__manifest": [("format", FORMAT), ("created_at", datetime.now().isoformat())],
            "__systems": [(s.id, s.name) for s in systems],
            "__equipment": [(x.id, x.name, x.alias) for x in equipment],
            "__sections": [(x.id, x.equipment_id, x.name) for x in sections],
            "__categories": [(x.id, x.name) for x in categories],
            "__parts": [(
                p.id, p.part_number, p.model_number, p.name,
                p.previous_part_id, p.equipment_id, p.section_id, p.category_id,
            ) for p in parts],
            "__stocks": hidden_stocks,
            "__alerts": [(a.system_id, a.part_id, a.threshold) for a in alerts],
        }
        for sheetname, rows in sheets.items():
            ws = writer.book.create_sheet(sheetname)
            ws.append(SCHEMAS[sheetname])
            for row in rows:
                ws.append(row)
                for cell in ws[ws.max_row]:
                    if isinstance(cell.value, str):
                        # Explicit string prevents hidden metadata being interpreted as formulas.
                        cell.data_type = "s"
            ws.sheet_state = "hidden"
        ws = writer.book["現在庫"]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col, width in {"A": 24, "B": 24, "C": 23, "D": 38, "E": 13, "F": 13, "G": 17}.items():
            ws.column_dimensions[col].width = width
    return output.getvalue()


def _table(book, name):
    if name not in book.sheetnames:
        raise InputError(f"メタデータシート {name} がありません")
    ws = book[name]
    if ws.sheet_state == "visible":
        raise InputError(f"メタデータシート {name} は非表示にしてください")
    rows = ws.iter_rows(values_only=True)
    header = next(rows, ())
    expected = SCHEMAS[name]
    if tuple(header[:len(expected)]) != expected:
        raise InputError(f"{name} の列定義が異なります")
    results = []
    for n, row in enumerate(rows, 2):
        if n > MAX_ROWS:
            raise InputError("Excelの行数が上限を超えています")
        if not any(v is not None for v in row):
            continue
        if len(row) > len(expected) and any(v is not None for v in row[len(expected):]):
            raise InputError(f"{name} の余分な列を削除してください")
        results.append(dict(zip(expected, row)))
    return results


def _records(rows, required_name, *, columns):
    mapping = {}
    for r in rows:
        rid = nonnegative(r.get("id"), f"{required_name} ID", allow_zero=False)
        if rid in mapping:
            raise InputError(f"{required_name} IDが重複しています")
        for name, length, mandatory in columns:
            r[name] = text_field(r.get(name) if r.get(name) is not None else "",
                                 f"{required_name} {name}", length, mandatory)
        mapping[rid] = r
    return mapping


def read_snapshot(blob):
    if len(blob) > MAX_XLSX_BYTES:
        raise InputError("ファイルサイズの上限は10MBです")
    if len(blob) < 4 or not blob.startswith(b"PK"):
        raise InputError("xlsx形式のファイルを選択してください")
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            if sum(f.file_size for f in z.infolist()) > MAX_INFLATED_BYTES:
                raise InputError("展開後のファイルサイズが上限を超えています")
        book = load_workbook(io.BytesIO(blob), read_only=False, data_only=True)
    except (zipfile.BadZipFile, OSError, ValueError, KeyError) as exc:
        raise InputError("Excelファイルを開けません") from exc
    try:
        manifest = dict((r["key"], r["value"]) for r in _table(book, "__manifest"))
        if manifest.get("format") != FORMAT:
            raise InputError("このExcelは対応する移植形式ではありません")

        systems = _records(_table(book, "__systems"), "システム", columns=[("name", 120, True)])
        equipment = _records(_table(book, "__equipment"), "機器", columns=[
            ("name", 160, True), ("alias", 160, False),
        ])
        categories = _records(_table(book, "__categories"), "分類", columns=[("name", 160, True)])
        sections = _records(_table(book, "__sections"), "部位", columns=[("name", 160, True)])
        parts = _records(_table(book, "__parts"), "部品", columns=[
            ("part_number", 160, True), ("model_number", 160, True),
            ("name", 250, True),
        ])
        if not systems:
            raise InputError("移植対象のシステムがありません")
        if len({r["name"] for r in systems.values()}) != len(systems):
            raise InputError("システム名が重複しています")

        def optref(value, mapping, label):
            if value is None or value == "":
                return None
            rid = nonnegative(value, label, allow_zero=False)
            if rid not in mapping:
                raise InputError(f"参照先の{label}が見つかりません")
            return rid

        for section in sections.values():
            section["equipment_id"] = optref(section.get("equipment_id"), equipment, "機器")
            if section["equipment_id"] is None:
                raise InputError("部位に機器が指定されていません")
        seen_identifiers = set()
        for part in parts.values():
            pair = (part["part_number"], part["model_number"])
            if pair in seen_identifiers:
                raise InputError("部品の品番と型式が重複しています")
            seen_identifiers.add(pair)
            for col, table, name in [
                ("previous_part_id", parts, "前版部品"), ("equipment_id", equipment, "機器"),
                ("section_id", sections, "部位"), ("category_id", categories, "分類"),
            ]:
                part[col] = optref(part.get(col), table, name)
            if part["section_id"] and (
                not part["equipment_id"]
                or sections[part["section_id"]]["equipment_id"] != part["equipment_id"]
            ):
                raise InputError("部位の所属機器が一致しません")
        # Topological order guards against circular and self-referential versions.
        sorted_parts = []
        pending = set(parts)
        while pending:
            ready = sorted(p for p in pending if parts[p]["previous_part_id"] not in pending)
            if not ready:
                raise InputError("品番・型式の新旧対応が循環しています")
            sorted_parts.extend(ready)
            pending.difference_update(ready)

        hidden_stock = {}
        for item in _table(book, "__stocks"):
            sid = optref(item.get("system_id"), systems, "システム")
            pid = optref(item.get("part_id"), parts, "部品")
            if (sid, pid) in hidden_stock:
                raise InputError("在庫のメタデータが重複しています")
            hidden_stock[(sid, pid)] = nonnegative(item.get("quantity"), "在庫")
        expected_pairs = {(sid, pid) for sid in systems for pid in parts}
        if set(hidden_stock) != expected_pairs:
            raise InputError("在庫メタデータの参照が不足しています")

        hidden_alerts = {}
        for item in _table(book, "__alerts"):
            sid = optref(item.get("system_id"), systems, "システム")
            pid = optref(item.get("part_id"), parts, "部品")
            if (sid, pid) in hidden_alerts:
                raise InputError("下限設定が重複しています")
            hidden_alerts[(sid, pid)] = nonnegative(item.get("threshold"), "下限値", allow_zero=False)

        visible_expected = {
            pair for pair, qty in hidden_stock.items()
            if qty > 0 or pair in hidden_alerts
        }
        ws = book["現在庫"] if "現在庫" in book else None
        if ws is None:
            raise InputError("現在庫シートがありません")
        iterator = ws.iter_rows(values_only=True)
        header = next(iterator, ())
        if tuple(header[:len(HEADERS)]) != HEADERS:
            raise InputError("現在庫シートの列定義が異なります")
        sys_by_name = {safe_excel(r["name"]): sid for sid, r in systems.items()}
        part_by_identity = {
            (safe_excel(r["part_number"]), safe_excel(r["model_number"])): pid
            for pid, r in parts.items()
        }
        shown = set()
        final_stock = dict(hidden_stock)
        final_alerts = dict(hidden_alerts)
        for rownum, row in enumerate(iterator, 2):
            if rownum > MAX_ROWS:
                raise InputError("現在庫一覧の行数が上限を超えています")
            if not any(v is not None for v in row):
                continue
            vals = dict(zip(HEADERS, row))
            sid = sys_by_name.get(vals.get("システム"))
            pid = part_by_identity.get((vals.get("品番"), vals.get("型式")))
            if sid is None or pid is None:
                raise InputError(f"{rownum}行目のシステムまたは部品がメタデータと一致しません")
            pair = (sid, pid)
            if pair in shown or pair not in visible_expected:
                raise InputError(f"{rownum}行目に重複・未登録の部品があります")
            if vals.get("品名") != safe_excel(parts[pid]["name"]):
                raise InputError(f"{rownum}行目の品名がメタデータと一致しません")
            shown.add(pair)
            final_stock[pair] = nonnegative(vals.get("現在庫"), "現在庫")
            alert = vals.get("下限値")
            if alert not in (None, ""):
                final_alerts[pair] = nonnegative(alert, "下限値", allow_zero=False)
            else:
                final_alerts.pop(pair, None)
        if shown != visible_expected:
            raise InputError("現在庫シートに不足している行があります。行は削除せず数量を0にしてください")

        return {
            "checksum": hashlib.sha256(blob).hexdigest(),
            "systems": systems, "equipment": equipment, "sections": sections,
            "categories": categories, "parts": parts, "sorted_parts": sorted_parts,
            "stock": final_stock, "alerts": final_alerts,
        }
    finally:
        book.close()


def preview_snapshot(payload):
    sysnames = [r["name"] for r in payload["systems"].values()]
    existing = set(SystemMaster.objects.filter(name__in=sysnames).values_list("name", flat=True))
    duplicate = StockImportBatch.objects.filter(checksum=payload["checksum"]).exists()
    return {
        "checksum": payload["checksum"],
        "systems": sysnames,
        "system_count": len(sysnames),
        "equipment_count": len(payload["equipment"]),
        "part_count": len(payload["parts"]),
        "opening_rows": sum(v > 0 for v in payload["stock"].values()),
        "quantity_total": sum(payload["stock"].values()),
        "alert_count": len(payload["alerts"]),
        "conflicts": sorted(existing),
        "already_imported": duplicate,
    }


def apply_snapshot(payload, *, rename=None):
    """Atomic, append-only fork. Never modifies a destination stock balance."""
    if rename is not None:
        rename = text_field(rename, "移植先システム名", 120)
        if len(payload["systems"]) != 1:
            raise InputError("システム名の変更は単一システムのファイルのみ対応します")
    system_names = {
        sid: rename if rename is not None else r["name"]
        for sid, r in payload["systems"].items()
    }
    with WRITE_LOCK, transaction.atomic():
        if StockImportBatch.objects.filter(checksum=payload["checksum"]).exists():
            raise InputError("このExcelファイルは既に取り込まれています")
        if SystemMaster.objects.filter(name__in=system_names.values()).exists():
            raise InputError("同名システムがあります。取り込み先システム名を変更してください")

        eq_map = {}
        for src_id, obj in payload["equipment"].items():
            target, _ = EquipmentMaster.objects.get_or_create(
                name=obj["name"], defaults={"alias": obj["alias"]},
            )
            if target.alias != obj["alias"]:
                raise InputError(f"機器『{target.name}』の通称が既存マスタと異なります")
            eq_map[src_id] = target.pk

        section_map = {}
        for src_id, obj in payload["sections"].items():
            target, _ = EquipmentSection.objects.get_or_create(
                equipment_id=eq_map[obj["equipment_id"]], name=obj["name"],
            )
            section_map[src_id] = target.pk

        cat_map = {}
        for src_id, obj in payload["categories"].items():
            target, _ = PartCategory.objects.get_or_create(name=obj["name"])
            cat_map[src_id] = target.pk

        part_map = {}
        for src_id in payload["sorted_parts"]:
            obj = payload["parts"][src_id]
            expected = {
                "name": obj["name"],
                "previous_part_id": part_map.get(obj["previous_part_id"]),
                "equipment_id": eq_map.get(obj["equipment_id"]),
                "section_id": section_map.get(obj["section_id"]),
                "category_id": cat_map.get(obj["category_id"]),
            }
            target, created = PartMaster.objects.get_or_create(
                part_number=obj["part_number"], model_number=obj["model_number"],
                defaults=expected,
            )
            if not created and any(getattr(target, key) != value for key, value in expected.items()):
                raise InputError(
                    f"部品『{target.part_number} / {target.model_number}』が既存マスタと異なります"
                )
            part_map[src_id] = target.pk
            if obj["previous_part_id"]:
                prior = payload["parts"][obj["previous_part_id"]]
                PartVersion.objects.get_or_create(
                    part_id=part_map[obj["previous_part_id"]],
                    old_part_number=prior["part_number"],
                    old_model_number=prior["model_number"],
                    new_part_number=obj["part_number"],
                    new_model_number=obj["model_number"],
                )

        system_map = {
            sid: SystemMaster.objects.create(name=name).pk
            for sid, name in system_names.items()
        }
        new_rows = []
        for (sid, pid), qty in payload["stock"].items():
            if qty:
                part_id = part_map[pid]
                part = payload["parts"][pid]
                new_rows.append(StockHistory(
                    system_id=system_map[sid], part_id=part_id,
                    direction=StockHistory.IN, quantity=qty,
                    operator="Excel移行",
                    note="Excel移植による期首在庫",
                    part_number_snapshot=part["part_number"],
                    model_number_snapshot=part["model_number"],
                ))
        StockHistory.objects.bulk_create(new_rows)
        StockAlertSetting.objects.bulk_create([
            StockAlertSetting(
                system_id=system_map[sid], part_id=part_map[pid], threshold=value,
            )
            for (sid, pid), value in payload["alerts"].items()
        ])
        StockImportBatch.objects.create(
            checksum=payload["checksum"], system_count=len(system_map),
            opening_rows=len(new_rows),
        )
        return {"systems": list(system_names.values()), "opening_rows": len(new_rows)}
