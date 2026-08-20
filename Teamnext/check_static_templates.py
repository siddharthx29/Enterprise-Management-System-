import os
import re
from pathlib import Path
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
django.setup()

from django.contrib.staticfiles.storage import staticfiles_storage

template_dir = Path('myapp/templates')
if not template_dir.exists():
    template_dir = Path('myapp/Templates')

missing_files = []

static_re = re.compile(r'{%\s*static\s+[\'"]([^\'"]+)[\'"]\s*%}')

for html_file in template_dir.glob('**/*.html'):
    content = html_file.read_text('utf-8')
    matches = static_re.findall(content)
    for m in matches:
        try:
            # this will raise ValueError in CompressedManifestStaticFilesStorage if file is missing and manifest is strictly enforced
            # But during normal collectstatic locally it might just return the path if manifest is not loaded dynamically
            # Let's just check if it exists in the storage physically
            if not staticfiles_storage.exists(m):
                missing_files.append((html_file.name, m))
        except Exception as e:
            missing_files.append((html_file.name, m, str(e)))

if missing_files:
    print("Found missing static files used in templates:")
    for mf in missing_files:
        print(mf)
else:
    print("All static files used in templates exist!")
