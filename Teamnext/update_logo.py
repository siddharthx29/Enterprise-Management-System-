import os

def replace_logo_in_templates():
    template_dir = r"c:\Users\HP\Desktop\Teamnext\Teamnext\myapp\Templates"
    old_logo = "myapp/images/teamnext_logo.png"
    new_logo = "myapp/images/logo.svg"
    
    for root, dirs, files in os.walk(template_dir):
        for file in files:
            if file.endswith(".html"):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if old_logo in content:
                    print(f"Updating {filepath}")
                    new_content = content.replace(old_logo, new_logo)
                    # Also update favicon type if it was png
                    new_content = new_content.replace('type="image/png" href="/static/myapp/images/teamnext_logo.png"', 'type="image/svg+xml" href="/static/myapp/images/logo.svg"')
                    
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(new_content)

if __name__ == "__main__":
    replace_logo_in_templates()
