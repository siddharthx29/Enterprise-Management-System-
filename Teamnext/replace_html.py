import re
with open('myapp/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove my previous botch jobs
# Target 1: The one-liner I added first
pattern1 = r", html_message=f\"\"\"<div style='font-family: Arial; padding: 20px; border: 1px solid #ddd; border-top: 4px solid #4a90e2; border-radius: 5px; background: #fafafa;'><h2 style='color: #333;'>TeamNext Security</h2><p>Hello,</p><p>We received a request to verify your account.</p><p style='font-size: 18px;'>Your OTP Code is: <strong style='color: #4a90e2; font-size: 24px;'>\{otp\}</strong></p><p>This code expires in 5 minutes. If you did not request this, please ignore this email.</p><br><p style='font-size: 12px; color: #777;'>Securely sent by TeamNext Enterprise Tool.</p></div>\"\"\""
content = re.sub(pattern1, "", content)

# Target 2: The multi-liner I added next
pattern2 = r",\s*html_message=f\"\"\"\s*<div style=\"font-family: Arial.*?Securely sent by TeamNext Enterprise Management Tool.</p>\s*</div>\s*\"\"\""
content = re.sub(pattern2, "", content, flags=re.DOTALL)

# Target 3 (similar variations if any)
pattern3 = r"fail_silently=False,\s*html_message=f\"\"\"\s*<div style=\"font-family: Arial.*?Securely sent by TeamNext Enterprise Management Tool.</p>\s*</div>\s*\"\"\""
content = re.sub(pattern3, "fail_silently=False", content, flags=re.DOTALL)

# Now inject it freshly
html_part = """fail_silently=False, 
            html_message=f\"\"\"
            <div style="font-family: Arial, sans-serif; padding: 30px; border-radius: 8px; background-color: #f9fafb; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb;">
                <h2 style="color: #2563eb; margin-top: 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;">TeamNext Enterprise Validation</h2>
                <p style="color: #374151; font-size: 16px;">Hello,</p>
                <p style="color: #374151; font-size: 16px;">We received a request to use this email address. Your OTP verification code is:</p>
                <div style="background-color: #eff6ff; padding: 15px; border-radius: 6px; text-align: center; margin: 25px 0; border: 1px dashed #93c5fd;">
                    <strong style="color: #1d4ed8; font-size: 32px; letter-spacing: 4px;">{otp}</strong>
                </div>
                <p style="color: #4b5563; font-size: 14px;">This code will expire in 5 minutes. If you did not request this, please safely ignore this email.</p>
                <p style="color: #9ca3af; font-size: 12px; margin-top: 30px; border-top: 1px solid #e5e7eb; padding-top: 15px;">Securely sent by TeamNext Enterprise Management Tool.</p>
            </div>
            \"\"\""""

content = content.replace("fail_silently=False", html_part)

with open('myapp/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
