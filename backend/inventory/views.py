"""Same-origin JSON API. State-changing requests are protected by Django CSRF."""
import io
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

from .models import PartMaster, PartVersion, StockAlertSetting, StockHistory, SystemMaster
from .services import (
    InputError, balance, change_part, correct_movement, create_movement,
    find_part, find_system, inventory_rows, positive_int, replace_alerts, text_field,
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
    }


def serialize_history(m, corrected_ids):
    return {
        "id": m.id, "system_id": m.system_id, "system": m.system.name,
        "part_id": m.part_id, "part_number": m.part_number_snapshot,
        "model_number": m.model_number_snapshot, "name": m.part.name,
        "direction": m.direction, "quantity": m.quantity,
        "company": m.company, "operator": m.operator, "note": m.note,
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
def parts(request):
    if request.method == "POST":
        data = body(request)
        p = PartMaster.objects.create(
            part_number=text_field(data.get("part_number"), "品番", 160),
            model_number=text_field(data.get("model_number"), "型式", 160),
            name=text_field(data.get("name"), "品名", 250),
        )
        return JsonResponse({"item": serialize_part(p)}, status=201)
    query = request.GET.get("q", "").strip()
    qs = PartMaster.objects.all()
    if query:
        from django.db.models import Q
        old_ids = PartVersion.objects.filter(
            Q(old_part_number__icontains=query) | Q(old_model_number__icontains=query)
        ).values_list("part_id", flat=True)
        qs = qs.filter(
            Q(part_number__icontains=query) | Q(model_number__icontains=query)
            | Q(name__icontains=query) | Q(pk__in=old_ids)
        )
    return JsonResponse({"items": [serialize_part(p) for p in qs.order_by("part_number", "model_number")[:500]]})


@endpoint(["PUT"])
def part_detail(request, pk):
    part = find_part(pk)
    part = change_part(part, body(request))
    return JsonResponse({"item": serialize_part(part)})


@endpoint(["GET"])
def part_versions(request, pk):
    part = find_part(pk)
    qs = part.versions.values(
        "id", "old_part_number", "old_model_number", "new_part_number", "new_model_number", "changed_at"
    )
    return JsonResponse({"items": list(qs)})


def system_param(request):
    raw = request.GET.get("system")
    return None if raw in (None, "") else find_system(raw).id


@endpoint(["GET"])
def stocks(request):
    system_id = system_param(request)
    all_items = request.GET.get("all") == "1"
    return JsonResponse({"items": inventory_rows(system_id, show_all=all_items)})


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
    import pandas as pd

    system_id = system_param(request)
    rows = inventory_rows(system_id)
    def excel_text(value):
        # Prevent untrusted master values from being interpreted as Excel formulas.
        return "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value

    data = [
        {
            "システム": excel_text(r["system"]), "品番": excel_text(r["part_number"]),
            "型式": excel_text(r["model_number"]), "品名": excel_text(r["name"]),
            "現在庫": r["quantity"], "下限値": r["threshold"],
            "警告": "下限以下" if r["alert"] else "",
        }
        for r in rows
    ]
    columns = ["システム", "品番", "型式", "品名", "現在庫", "下限値", "警告"]
    stream = io.BytesIO()
    pd.DataFrame(data, columns=columns).to_excel(stream, sheet_name="現在庫", index=False, engine="openpyxl")
    stream.seek(0)
    response = FileResponse(
        stream,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="spare_parts_stock.xlsx"'
    return response


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
