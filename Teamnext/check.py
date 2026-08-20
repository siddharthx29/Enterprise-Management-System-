import re

with open('myapp/views.py', 'r', encoding='utf-8') as f:
    orig = f.read()

print("Occurrences of 'def login_view(request):':", orig.count('def login_view(request):'))
print("Occurrences of 'send_mail(': ", orig.count('send_mail('))
