import os
import re

files = [
    'finance_page.html', 'hr_page.html', 'inventory_page.html', 'reports_page.html',
    'analytics_page.html', 'chat_page.html', 'leaves_page.html', 'projects_page.html',
    'social_page.html', 'tickets.html', 'users_page.html', 'settings_page.html', 'profile_page.html'
]

brand_replacement = '''<div class="brand" style="display:flex; align-items:center; gap:12px;">
                <div
                    style="width:42px; height:42px; border-radius:10px; background:#ffffff; padding:4px; display:flex; align-items:center; justify-content:center; box-shadow:0 2px 8px rgba(0,0,0,0.1); flex-shrink:0;">
                    <img src="{% static 'myapp/images/teamnext_logo.png' %}" alt="TeamNext"
                        style="width:100%; height:100%; object-fit:contain;">
                </div>
                <div>
                    <div class="logo">TeamNext</div>
                    <div style="font-size:10px; color:#94a3b8; letter-spacing:0.05em; margin-top:1px;">Enterprise
                        Management</div>
                </div>
            </div>'''
            
for file_name in files:
    path = os.path.join(r"c:\Users\HP\Desktop\Teamnext\Teamnext\myapp\Templates", file_name)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        changed = False

        if '{% load static %}' not in content:
            content = '{% load static %}\n' + content
            changed = True

        if '<div class="brand">' in content:
            content = re.sub(r'<div class="brand">\s*<div class="logo">TeamNext</div>\s*</div>', brand_replacement, content)
            changed = True
            
        if changed:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated {file_name}")

