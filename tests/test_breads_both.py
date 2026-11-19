"""Regression test for shared first-course bread visibility in Excel imports."""
from io import BytesIO

from openpyxl import Workbook

from app.menu_excel import parse_menu_workbook


def test_breads_shared_even_if_old_excel_says_veg_or_blank():
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Menu Import"
    sheet.append(["Item ID", "Main Category", "South Indian", "North Indian", "Sub Category", "Menu Section", "Menu Item Name", "Item Image", "Display Price (€)", "Display Order", "Active", "Notes", "Food Description", "Image Filename Label (.webp)"])
    sheet.append([43, None, "Yes", "Yes", "First Course", "Breads & Staples", "Appam", "https://example.com/0043-appam.webp", None, 1, "Yes", "", "", "0043-appam.webp"])
    sheet.append([35, "Veg Cuisine", "Yes", "Yes", "First Course", "Breads & Staples", "Plain Naan", "https://example.com/0035-plain-naan.webp", None, 2, "Yes", "", "", "0035-plain-naan.webp"])
    sheet.append([110, "Veg Cuisine", "Yes", "Yes", "First Course", "Veg Curries", "Test Veg Curry", "https://example.com/curry.webp", None, 3, "Yes"])
    sheet.append([111, "Non Veg Cuisine", "Yes", "Yes", "First Course", "Non Veg Curries", "Test Non Veg Curry", "https://example.com/chicken.webp", None, 4, "Yes"])
    buff = BytesIO()
    wb.save(buff)
    parsed = parse_menu_workbook(buff.getvalue())
    by_id = {item["item_id"]: item for item in parsed["items"]}
    assert by_id[43]["dietary"] == "both"
    assert by_id[35]["dietary"] == "both"
    assert by_id[110]["dietary"] == "veg"
    assert by_id[111]["dietary"] == "nonveg"
    assert by_id[43]["image_reference"] == "https://example.com/0043-appam.webp"
    assert by_id[35]["regions"] == ["South Indian", "North Indian"]
