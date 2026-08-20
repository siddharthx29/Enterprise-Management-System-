import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
os.environ['DEBUG'] = 'False'
django.setup()

from django.test import Client
from django.conf import settings
print("ALLOWED_HOSTS:", settings.ALLOWED_HOSTS)

print("Starting request...")
try:
    c = Client(SERVER_NAME='teamnexterp.com')
    response = c.get('/')
    print("Status Code:", response.status_code)
except Exception as e:
    print("Exception:", type(e).__name__, "-", str(e))
    import traceback
    traceback.print_exc()
