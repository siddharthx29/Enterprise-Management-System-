import os

def fix_favicon_type():
    template_dir = r"c:\Users\HP\Desktop\Teamnext\Teamnext\myapp\Templates"
    target = 'type="image/png" href="/static/myapp/images/logo.svg"'
    replacement = 'type="image/svg+xml" href="/static/myapp/images/logo.svg"'
    
    for root, dirs, files in os.walk(template_dir):
        for file in files:
            if file.endswith(".html"):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if target in content:
                    print(f"Fixing type in {filepath}")
                    new_content = content.replace(target, replacement)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(new_content)

if __name__ == "__main__":
    fix_favicon_type()
