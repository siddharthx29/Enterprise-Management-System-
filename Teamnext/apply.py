import re

with open('myapp/views.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Step 1: Fix nsb566@gmail.com
text = text.replace('\"nsb566@gmail.com\"', 'settings.EMAIL_HOST_USER')

# Step 2: Inject HTML template for OTP emails
# Let's find all the 'fail_silently=False' that are inside an OTP send_mail function
# send_otp, api_send_otp_json, resend_otp, _send_signup_otp
html_addon = \
"fail_silently=False,\n" + \
"            html_message=f\"\"\"\n" + \
"            <div style='font-family: Arial, sans-serif; padding: 30px; border-radius: 8px; background-color: #f9fafb; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb;'>\n" + \
"                <h2 style='color: #2563eb; margin-top: 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;'>TeamNext Enterprise Validation</h2>\n" + \
"                <p style='color: #374151; font-size: 16px;'>Hello,</p>\n" + \
"                <p style='color: #374151; font-size: 16px;'>We received a request for an account verification or login. Your OTP verification code is:</p>\n" + \
"                <div style='background-color: #eff6ff; padding: 15px; border-radius: 6px; text-align: center; margin: 25px 0; border: 1px dashed #93c5fd;'>\n" + \
"                    <strong style='color: #1d4ed8; font-size: 32px; letter-spacing: 4px;'>{otp}</strong>\n" + \
"                </div>\n" + \
"                <p style='color: #4b5563; font-size: 14px;'>This code will expire in 5 minutes. If you did not request this, please safely ignore this email.</p>\n" + \
"                <p style='color: #9ca3af; font-size: 12px; margin-top: 30px; border-top: 1px solid #e5e7eb; padding-top: 15px;'>Securely sent by TeamNext Enterprise Management Tool.</p>\n" + \
"            </div>\n" + \
"            \"\"\""

def replacer(match):
    original = match.group(0)
    # Check if {otp} is in the call
    if '{otp}' in original:
         return original.replace("fail_silently=False", html_addon)
    else:
         return original

new_text = re.sub(r'send_mail\([\s\S]*?fail_silently=False[\s\S]*?\)', replacer, text)

# Step 3: Fix fail_silently=True inside add_developer
dev_target = 'fail_silently=True,\n\n        )'
if "Developer Verification OTP" in new_text:
    
    html_addon_dev = \
    "fail_silently=True,\n" + \
    "            html_message=f\"\"\"\n" + \
    "            <div style='font-family: Arial, sans-serif; padding: 30px; border-radius: 8px; background-color: #f9fafb; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb;'>\n" + \
    "                <h2 style='color: #2563eb; margin-top: 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;'>TeamNext Developer Access</h2>\n" + \
    "                <p style='color: #374151; font-size: 16px;'>Hello,</p>\n" + \
    "                <p style='color: #374151; font-size: 16px;'>A developer '<b>{name}</b>' ({email}) is being added to your workspace. The verification OTP is:</p>\n" + \
    "                <div style='background-color: #eff6ff; padding: 15px; border-radius: 6px; text-align: center; margin: 25px 0; border: 1px dashed #93c5fd;'>\n" + \
    "                    <strong style='color: #1d4ed8; font-size: 32px; letter-spacing: 4px;'>{otp}</strong>\n" + \
    "                </div>\n" + \
    "                <p style='color: #4b5563; font-size: 14px;'>It expires in 5 minutes.</p>\n" + \
    "                <p style='color: #9ca3af; font-size: 12px; margin-top: 30px; border-top: 1px solid #e5e7eb; padding-top: 15px;'>Securely sent by TeamNext Enterprise Management Tool.</p>\n" + \
    "            </div>\n" + \
    "            \"\"\"\n        )"
    
    # We regex replace the exact add_developer block
    new_text = re.sub(r'(send_mail\(\s*"Developer Verification OTP - TeamNext"[\s\S]*?)fail_silently=True,\s*\)', r'\1' + html_addon_dev, new_text)

with open('myapp/views.py', 'w', encoding='utf-8') as f:
    f.write(new_text)

