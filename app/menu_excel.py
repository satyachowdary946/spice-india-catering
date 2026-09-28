from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from openpyxl import load_workbook


YES_VALUES = {"yes", "y", "true", "1", "active"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _yes(value: Any, default: bool = False) -> bool:
    text = _text(value).casefold()
    if not text:
        return default
    return text in YES_VALUES


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _find_header(ws, required: str, max_rows: int = 12) -> tuple[int, dict[str, int]]:
    for row in range(1, min(ws.max_row, max_rows) + 1):
        headers: dict[str, int] = {}
        for col in range(1, ws.max_column + 1):
            value = _text(ws.cell(row, col).value)
            if value:
                headers[value] = col
        if required in headers:
            return row, headers
    raise ValueError(f"Could not find the '{required}' header in sheet '{ws.title}'.")


def parse_menu_workbook(data: bytes) -> dict[str, Any]:
    """Parse the catering import workbook without mutating the database."""
    try:
        wb = load_workbook(BytesIO(data), data_only=False, read_only=False)
    except Exception as exc:
        raise ValueError("The uploaded file is not a readable .xlsx workbook.") from exc

    if "Menu Import" not in wb.sheetnames:
        raise ValueError("Workbook must contain a 'Menu Import' sheet.")

    ws = wb["Menu Import"]
    header_row, headers = _find_header(ws, "Item ID")
    required = ["Item ID", "Main Category", "Sub Category", "Menu Section", "Menu Item Name", "Display Order", "Active"]
    missing = [name for name in required if name not in headers]
    if missing:
        raise ValueError("Menu Import is missing columns: " + ", ".join(missing))

    # Region columns are intentionally dynamic: every column between Main Category and Sub Category.
    main_col = headers["Main Category"]
    sub_col = headers["Sub Category"]
    region_columns: list[tuple[str, int]] = []
    for col in range(main_col + 1, sub_col):
        name = _text(ws.cell(header_row, col).value)
        if name:
            region_columns.append((name, col))

    items: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for row in range(header_row + 1, ws.max_row + 1):
        raw_id = ws.cell(row, headers["Item ID"]).value
        name = _text(ws.cell(row, headers["Menu Item Name"]).value)
        if raw_id in (None, "") and not name:
            continue
        item_id = _int(raw_id, -1)
        if item_id <= 0:
            raise ValueError(f"Menu Import row {row}: Item ID must be a positive whole number.")
        if item_id in seen_ids:
            raise ValueError(f"Menu Import row {row}: duplicate Item ID {item_id}.")
        seen_ids.add(item_id)
        if not name:
            raise ValueError(f"Menu Import row {row}: Menu Item Name is required.")

        main_category = _text(ws.cell(row, headers["Main Category"]).value)
        main_key = main_category.casefold()
        if "non" in main_key and "veg" in main_key:
            dietary = "nonveg"
        elif main_key == "both" or "both" in main_key:
            dietary = "both"
        else:
            dietary = "veg"

        regions = [region_name for region_name, col in region_columns if _yes(ws.cell(row, col).value, False)]
        if not regions:
            regions = [region_name for region_name, _ in region_columns]

        items.append({
            "item_id": item_id,
            "main_category": main_category,
            "dietary": dietary,
            "regions": regions,
            "category": _text(ws.cell(row, headers["Sub Category"]).value) or "Other",
            "section": _text(ws.cell(row, headers["Menu Section"]).value) or "Main Selection",
            "name": name,
            "image_reference": _text(ws.cell(row, headers.get("Item Image", 0)).value) if headers.get("Item Image") else "",
            "sort_order": _int(ws.cell(row, headers["Display Order"]).value, 0),
            "active": _yes(ws.cell(row, headers["Active"]).value, True),
            "notes": _text(ws.cell(row, headers.get("Notes", 0)).value) if headers.get("Notes") else "",
        })

    side_filters: list[dict[str, Any]] = []
    if "Category Setup" in wb.sheetnames:
        setup = wb["Category Setup"]
        try:
            setup_header, sh = _find_header(setup, "Type")
            for row in range(setup_header + 1, setup.max_row + 1):
                if _text(setup.cell(row, sh["Type"]).value).casefold() == "side filter":
                    side_filters.append({
                        "name": _text(setup.cell(row, sh.get("Name", 0)).value),
                        "sort_order": _int(setup.cell(row, sh.get("Display Order", 0)).value, 0),
                    })
        except ValueError:
            pass
    if not side_filters:
        side_filters = [{"name": name, "sort_order": idx + 1} for idx, (name, _) in enumerate(region_columns)]
    side_filters = [f for f in side_filters if f["name"]]

    combinations: list[dict[str, Any]] | None = None
    if "Combinations" in wb.sheetnames:
        combinations = []
        cw = wb["Combinations"]
        try:
            combo_header, ch = _find_header(cw, "Trigger Item ID")
            required_combo = ["Trigger Item ID", "Recommended Item ID", "Priority", "Active", "Reciprocal"]
            missing_combo = [name for name in required_combo if name not in ch]
            if missing_combo:
                raise ValueError("Combinations is missing columns: " + ", ".join(missing_combo))
            for row in range(combo_header + 1, cw.max_row + 1):
                trigger_raw = cw.cell(row, ch["Trigger Item ID"]).value
                rec_raw = cw.cell(row, ch["Recommended Item ID"]).value
                if trigger_raw in (None, "") and rec_raw in (None, ""):
                    continue
                trigger = _int(trigger_raw, -1)
                recommended = _int(rec_raw, -1)
                if trigger <= 0 or recommended <= 0:
                    raise ValueError(f"Combinations row {row}: Trigger and Recommended Item IDs must be positive numbers.")
                if trigger == recommended:
                    raise ValueError(f"Combinations row {row}: an item cannot recommend itself.")
                if trigger not in seen_ids:
                    raise ValueError(f"Combinations row {row}: Trigger Item ID {trigger} is not in Menu Import.")
                if recommended not in seen_ids:
                    raise ValueError(f"Combinations row {row}: Recommended Item ID {recommended} is not in Menu Import.")
                combinations.append({
                    "trigger_item_id": trigger,
                    "recommended_item_id": recommended,
                    "priority": max(1, _int(cw.cell(row, ch["Priority"]).value, 1)),
                    "active": _yes(cw.cell(row, ch["Active"]).value, True),
                    "reciprocal": _yes(cw.cell(row, ch["Reciprocal"]).value, False),
                    "popup_title": _text(cw.cell(row, ch.get("Popup Title", 0)).value) if ch.get("Popup Title") else "",
                    "notes": _text(cw.cell(row, ch.get("Notes", 0)).value) if ch.get("Notes") else "",
                })
        except ValueError as exc:
            raise exc

    return {
        "items": items,
        "side_filters": side_filters,
        "combinations": combinations,
        "region_columns": [name for name, _ in region_columns],
    }
