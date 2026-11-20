"""Regression: admin reset UI stays removed; CLI is operator-only."""
from pathlib import Path
from app.main import app

def test_no_admin_reset_controls():
    paths = {route.path for route in app.routes}
    assert "/admin/settings/data-management" not in paths
    assert "/admin/settings/data-management/reset" not in paths
    source = Path(__file__).resolve().parents[1] / "app/templates/admin/settings.html"
    assert "Open Data Management" not in source.read_text()
