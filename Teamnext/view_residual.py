import re

with open('myapp/views.py', 'r', encoding='utf-8') as f:
    text = f.read()

matches = re.findall(r"(send_mail\([\s\S]{0,150}\))", text)
for i, m in enumerate(matches):
    print(f"Match {i+1}:\n{m}\n")
