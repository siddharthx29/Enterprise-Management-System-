import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
os.environ["DEBUG"] = "False"

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()

def start_response(status, headers, exc_info=None):
    print("Status:", status)

from io import BytesIO
environ = {
    'REQUEST_METHOD': 'GET',
    'SERVER_NAME': 'teamnexterp.com',
    'SERVER_PORT': '80',
    'PATH_INFO': '/',
    'wsgi.url_scheme': 'http',
    'wsgi.input': BytesIO(b""),
    'HTTP_HOST': 'teamnexterp.com'
}

response = application(environ, start_response)
print("Response headers generated.")
