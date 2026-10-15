import io
"""Same-origin JSON API. State-changing requests are protected by Django CSRF."""
import json
import mimetypes
import sqlite3
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError
from django.http import FileResponse, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .transfer import write_snapshot, read_snapshot, preview_snapshot, apply_snapshot, MAX_XLSX_BYTES
from .models import EquipmentMaster, EquipmentSection, PartCategory, PartMaster, PartVersion, StockAlertSetting, StockHistory, SystemMaster
from .services import (
    InputError, balance, change_part, correct_movement, create_movement,
    find_part, find_system, inventory_rows, part_assignments, positive_int, replace_alerts, text_field,
)


def endpoint(methods):
    def decorate(func):
        @wraps(func)
        @require_http_methods(methods)
        def handler(request, *args, **kwargs):
            try:
                return func(request, *args, **kwargs)
            except (InputError, ValueError) as ex:
                return JsonResponse({"error": str(ex)}, status=400)
            except IntegrityError:
                return JsonResponse({"error": "重複または参照整合性エラーです"}, status=409)
        return handler
    return decorate


def body(request):
    try:
        parsed = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise InputError("JSONの形式が不正です") from None
    if not isinstance(parsed, dict):
        raise InputError("JSONオブジェクトを指定してください")
    return parsed


def serialize_part(part):
    return {
        "id": part.id, "part_number": part.part_number,
        "model_number": part.model_number, "name": part.name,
        "previous_part_id": part.previous_part_id, "equipment_id": part.equipment_id,
        "section_id": part.section_id, "category_id": part.category_id,
    }


def serialize_history(m, corrected_ids):
    return {
        "id": m.id, "system_id": m.system_id, "system": m.system.name,
        "part_id": m.part_id, "part_number": m.part_number_snapshot,
        "model_number": m.model_number_snapshot, "name": m.part.name,
        "direction": m.direction, "quantity": m.quantity,
        "operator": m.operator, "note": m.note,
        "reversal_of": m.reversal_of_id, "corrected": m.id in corrected_ids,
        "created_at": m.created_at.isoformat(),
    }


@ensure_csrf_cookie
@endpoint(["GET"])
def health(request):
    get_token(request)
    return JsonResponse({"ok": True})


@endpoint(["GET", "POST"])
def systems(request):
    if request.method == "GET":
        return JsonResponse({"items": list(SystemMaster.objects.values("id", "name"))})
    data = body(request)
    name = text_field(data.get("name"), "システム名", 120)
    s = SystemMaster.objects.create(name=name)
    return JsonResponse({"item": {"id": s.id, "name": s.name}}, status=201)


@endpoint(["PUT"])
def system_detail(request, pk):
    system = find_system(pk)
    system.name = text_field(body(request).get("name"), "システム名", 120)
    system.save(update_fields=["name"])
    return JsonResponse({"item": {"id": system.id, "name": system.name}})


@endpoint(["GET", "POST"])
def equipment(request):
    if request.method == "GET":
        return JsonResponse({"items": list(EquipmentMaster.objects.values("id", "name", "alias"))})
    data = body(request)
    item = EquipmentMaster.objects.create(
        name=text_field(data.get("name"), "機器名", 160),
        alias=text_field(data.get("alias", ""), "機器通称", 160, required=False),
    )
    return JsonResponse({"item": {"id": item.pk, "name": item.name, "alias": item.alias}}, status=201)


@endpoint(["PUT"])
def equipment_detail(request, pk):
    try:
        item = EquipmentMaster.objects.get(pk=pk)
    except EquipmentMaster.DoesNotExist:
        raise InputError("機器が存在しません") from None
    data = body(request)
    item.name = text_field(data.get("name"), "機器名", 160)
    item.alias = text_field(data.get("alias", ""), "機器通称", 160, required=False)
    item.save(update_fields=["name", "alias"])
    return JsonResponse({"item": {"id": item.pk, "name": item.name, "alias": item.alias}})


@endpoint(["GET", "POST"])
def equipment_sections(request):
    if request.method == "GET":
        return JsonResponse({"items": list(
            EquipmentSection.objects.values("id", "equipment_id", "name")
        )})
    data = body(request)
    equipment_id = positive_int(data.get("equipment_id"), "機器ID")
    if not EquipmentMaster.objects.filter(pk=equipment_id).exists():
        raise InputError("機器が存在しません")
    item = EquipmentSection.objects.create(
        equipment_id=equipment_id,
        name=text_field(data.get("name"), "部位名", 160),
    )
    return JsonResponse({"item": {
        "id": item.pk, "equipment_id": item.equipment_id, "name": item.name
    }}, status=201)


@endpoint(["PUT"])
def equipment_section_detail(request, pk):
    try:
        item = EquipmentSection.objects.get(pk=pk)
    except EquipmentSection.DoesNotExist:
        raise InputError("部位が存在しません") from None
    data = body(request)
    item.name = text_field(data.get("name"), "部位名", 160)
    item.save(update_fields=["name"])
    return JsonResponse({"item": {
        "id": item.pk, "equipment_id": item.equipment_id, "name": item.name
    }})


@endpoint(["GET", "POST"])
def categories(request):
    if request.method == "GET":
        return JsonResponse({"items": list(PartCategory.objects.values("id", "name"))})
    data = body(request)
    item = PartCategory.objects.create(name=text_field(data.get("name"), "分類名", 160))
    return JsonResponse({"item": {"id": item.pk, "name": item.name}}, status=201)


@endpoint(["PUT"])
def category_detail(request, pk):
    try:
        item = PartCategory.objects.get(pk=pk)
    except PartCategory.DoesNotExist:
        raise InputError("分類が存在しません") from None
    item.name = text_field(body(request).get("name"), "分類名", 160)
    item.save(update_fields=["name"])
    return JsonResponse({"item": {"id": item.pk, "name": item.name}})


@endpoint(["GET", "POST"])
def parts(request):
    if request.method == "POST":
        data = body(request)
        p = PartMaster.objects.create(
            part_number=text_field(data.get("part_number"), "品番", 160),
            model_number=text_field(data.get("model_number"), "型式", 160),
            name=text_field(data.get("name"), "品名", 250),
            **part_assignments(data),
        )
        return JsonResponse({"item": serialize_part(p)}, status=201)
    query = request.GET.get("q", "").strip()
    qs = PartMaster.objects.all()
    filter_ids = {
        "equipment_id": request.GET.get("equipment"),
        "section_id": request.GET.get("section"),
        "category_id": request.GET.get("category"),
    }
    for field, value in filter_ids.items():
        if value not in (None, ""):
            qs = qs.filter(**{field: positive_int(value, field)})
    if query:
        from django.db.models import Q
        old_ids = PartVersion.objects.filter(
            Q(old_part_number__icontains=query) | Q(old_model_number__icontains=query)
        ).values_list("part_id", flat=True)
        qs = qs.filter(
            Q(part_number__icontains=query) | Q(model_number__icontains=query)
            | Q(name__icontains=query) | Q(pk__in=old_ids)
        )
    return JsonResponse({"items": [serialize_part(p) for p in qs.order_by("part_number", "model_number")]})


@endpoint(["PUT"])
def part_detail(request, pk):
    part = find_part(pk)
    part = change_part(part, body(request))
    return JsonResponse({"item": serialize_part(part)})


@endpoint(["GET"])
def part_versions(request, pk):
    part = find_part(pk)
    # Also return earlier identifier changes for the selected successor.
    lineage = [part.pk]
    ancestor = part.previous_part_id
    while ancestor is not None and ancestor not in lineage:
        lineage.append(ancestor)
        ancestor = PartMaster.objects.filter(pk=ancestor).values_list(
            "previous_part_id", flat=True
        ).first()
    qs = PartVersion.objects.filter(part_id__in=lineage).values(
        "id", "old_part_number", "old_model_number", "new_part_number",
        "new_model_number", "changed_at"
    ).order_by("-changed_at", "-id")
    return JsonResponse({"items": list(qs)})


def system_param(request):
    raw = request.GET.get("system")
    return None if raw in (None, "") else find_system(raw).id


def filter_inventory_rows(request, rows):
    """Allow reverse lookup by equipment, section and category across stock views."""
    filters = {}
    for field, param in (
        ("equipment_id", "equipment"), ("section_id", "section"),
        ("category_id", "category"),
    ):
        raw = request.GET.get(param)
        if raw not in (None, ""):
            filters[field] = positive_int(raw, param)
    if not filters:
        return rows
    ids = set(PartMaster.objects.filter(**filters).values_list("pk", flat=True))
    return [row for row in rows if row["part_id"] in ids]


@endpoint(["GET"])
def stocks(request):
    system_id = system_param(request)
    all_items = request.GET.get("all") == "1"
    rows = filter_inventory_rows(request, inventory_rows(system_id, show_all=all_items))
    return JsonResponse({"items": rows})


@endpoint(["GET", "POST"])
def history(request):
    if request.method == "POST":
        obj = create_movement(body(request))
        return JsonResponse({"id": obj.pk, "balance": balance(obj.system_id, obj.part_id)}, status=201)
    system_id = system_param(request)
    records = StockHistory.objects.select_related("system", "part")
    if system_id:
        records = records.filter(system_id=system_id)
    records = list(records[:500])
    corrected_ids = set(
        StockHistory.objects.filter(reversal_of_id__in=[r.id for r in records])
        .values_list("reversal_of_id", flat=True)
    )
    return JsonResponse({"items": [serialize_history(r, corrected_ids) for r in records]})


@endpoint(["POST"])
def history_correct(request, pk):
    reverse, revised = correct_movement(pk, body(request))
    return JsonResponse({
        "reversal_id": reverse.pk, "replacement_id": revised.pk,
        "balance": balance(revised.system_id, revised.part_id),
    }, status=201)


@endpoint(["GET"])
def alerts(request):
    system = find_system(request.GET.get("system"))
    return JsonResponse({"items": list(
        StockAlertSetting.objects.filter(system=system).values("part_id", "threshold")
    )})


@endpoint(["POST"])
def alerts_bulk(request):
    data = body(request)
    system = find_system(data.get("system_id"))
    count = replace_alerts(system, data.get("items"))
    return JsonResponse({"count": count})


@endpoint(["GET"])
def export_excel(request):
    system_id = system_param(request)
    filters = {}
    for field, param in (
        ("equipment_id", "equipment"), ("section_id", "section"),
        ("category_id", "category"),
    ):
        value = request.GET.get(param)
        if value not in (None, ""):
            filters[field] = positive_int(value, param)
    stream = io.BytesIO(write_snapshot(system_id, filters))
    response = FileResponse(
        stream, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="spare_parts_stock.xlsx"'
    return response


def uploaded_snapshot(request):
    document = request.FILES.get("file")
    if not document:
        raise InputError("取り込むExcelファイルを選択してください")
    if document.size > MAX_XLSX_BYTES:
        raise InputError("Excelファイルが10MBを超えています")
    return read_snapshot(document.read())


@endpoint(["POST"])
def import_preview(request):
    return JsonResponse(preview_snapshot(uploaded_snapshot(request)))


@endpoint(["POST"])
def import_apply(request):
    payload = uploaded_snapshot(request)
    rename = request.POST.get("system_name")
    result = apply_snapshot(payload, rename=rename if rename else None)
    return JsonResponse(result, status=201)


@endpoint(["POST"])
def backup(request):
    folder = settings.DATA_DIR / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = folder / f"inventory_{stamp}.sqlite3"
    with sqlite3.connect(str(settings.DATABASES["default"]["NAME"])) as source:
        with sqlite3.connect(str(destination)) as target:
            source.backup(target)
    return JsonResponse({"filename": destination.name})


@ensure_csrf_cookie
def index(request):
    dist = settings.BASE_DIR / "frontend" / "dist" / "index.html"
    if not dist.is_file():
        return HttpResponse(
            "Reactのビルドがありません。frontendで npm ci / npm run build を実行してください。",
            status=503, content_type="text/plain; charset=utf-8",
        )
    return HttpResponse(dist.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")


def asset(request, filepath):
    root = (settings.BASE_DIR / "frontend" / "dist" / "assets").resolve()
    target = (root / filepath).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        return HttpResponse(status=404)
    mime, _ = mimetypes.guess_type(target.name)
    return FileResponse(target.open("rb"), content_type=mime or "application/octet-stream")


@endpoint(["GET"])
def favicon(request):
    """Serve the exact ICO bundled into the native Windows executable."""
    icon = settings.BASE_DIR / "assets" / "spare_parts.ico"
    if not icon.is_file():
        return HttpResponse(status=404)
    return FileResponse(icon.open("rb"), content_type="image/x-icon")
