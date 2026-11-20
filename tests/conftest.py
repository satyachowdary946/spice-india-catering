"""Always isolate automated tests from the live Render database and providers.

Loaded by pytest before any app import; overrides local .env/production shell
variables for this test process only. Never deploy using a test configuration.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ['DATABASE_URL'] = f"sqlite:///{ROOT / 'tests' / 'test_catering.db'}"
os.environ['SESSION_SECRET'] = 'test-secret-only-for-disposable-database'
os.environ['RENDER'] = ''
os.environ['RESEND_API_KEY'] = ''
os.environ['RESEND_FROM_EMAIL'] = ''
os.environ['WHATSAPP_CLOUD_TOKEN'] = ''
os.environ['WHATSAPP_PHONE_NUMBER_ID'] = ''
os.environ['ADMIN_WHATSAPP_TO'] = ''
