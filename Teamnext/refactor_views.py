import re

with open('myapp/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

helper_function = """
def send_otp_email(recipient_email, otp, subject="TeamNext Enterprise Validation", context_msg="We received a request to verify your account."):
    html_message = f\"\"\"
    <div style="font-family: Arial, sans-serif; padding: 30px; border-radius: 8px; background-color: #f9fafb; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb;">
        <h2 style="color: #2563eb; margin-top: 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;">{subject}</h2>
        <p style="color: #374151; font-size: 16px;">Hello,</p>
        <p style="color: #374151; font-size: 16px;">{context_msg} Your OTP verification code is:</p>
        <div style="background-color: #eff6ff; padding: 15px; border-radius: 6px; text-align: center; margin: 25px 0; border: 1px dashed #93c5fd;">
            <strong style="color: #1d4ed8; font-size: 32px; letter-spacing: 4px;">{otp}</strong>
        </div>
        <p style="color: #4b5563; font-size: 14px;">This code will expire in 5 minutes. If you did not request this, please safely ignore this email.</p>
        <p style="color: #9ca3af; font-size: 12px; margin-top: 30px; border-top: 1px solid #e5e7eb; padding-top: 15px;">Securely sent by TeamNext Enterprise Management Tool.</p>
    </div>
    \"\"\"
    plain_message = f"Hello,\\n\\n{context_msg}\\nYour OTP is: {otp}\\n\\nExpires in 5 minutes."
    
    # Check if recipient_email is a list
    if not isinstance(recipient_email, list):
        recipient_email = [recipient_email]
        
    send_mail(
        subject,
        plain_message,
        settings.EMAIL_HOST_USER,
        recipient_email,
        fail_silently=False,
        html_message=html_message
    )

def login_view(request):"""

if "def send_otp_email" not in content:
    content = content.replace("def login_view(request):", helper_function, 1)

# Now, we regex replace the giant blocks of send_mail in the targeted functions.

# 1. send_otp block
pattern_send_otp = r"send_mail\(\s*\"Your OTP Code - TeamNext Enterprise Management Tool\",\s*f\"\"\"[\s\S]*?fail_silently=False,\s*html_message=f\"\"\"[\s\S]*?\"\"\"\s*\)"

content = re.sub(pattern_send_otp, "send_otp_email(email, otp, subject='TeamNext Login Verification', context_msg='A request was made to login to your account.')", content)


# 2. api_send_otp_json block
pattern_api = r"send_mail\(\s*\"Verify Your Account - TeamNext Enterprise Management Tool\",\s*msg,\s*settings\.EMAIL_HOST_USER,\s*recipients,\s*fail_silently=False,\s*html_message=f\"\"\"[\s\S]*?\"\"\"\s*\)"

content = re.sub(pattern_api, "send_otp_email(recipients, otp, subject='TeamNext Workspace Verification', context_msg='We received a request for an account registration/verification.')", content)

# 3. resend_otp block
pattern_resend = r"send_mail\(\s*\"New OTP Code - TeamNext Enterprise Management Tool\",\s*f\"\"\"[\s\S]*?fail_silently=False,\s*html_message=f\"\"\"[\s\S]*?\"\"\"\s*\)"

content = re.sub(pattern_resend, "send_otp_email(email, otp, subject='TeamNext - New OTP Requested', context_msg='You requested a new OTP code.')", content)


# 4. _send_signup_otp block
pattern_signup = r"send_mail\(\s*\"Verify Your Account - TeamNext Enterprise Management Tool\",\s*f\"Hello,\\n\\nYour OTP for account verification is: \{otp\}\\n\\nExpires in 5 minutes\.\",\s*settings\.EMAIL_HOST_USER,\s*\[email\],\s*fail_silently=False,\s*html_message=f\"\"\"[\s\S]*?\"\"\"\s*\)"

content = re.sub(pattern_signup, "send_otp_email(email, otp, subject='TeamNext Workspace Registration', context_msg='We received a request to register your workspace.')", content)


# 5. add_developer block
pattern_dev = r"send_mail\(\s*\"Developer Verification OTP - TeamNext\",\s*f\"Hello,\\n\\nA developer '\{name\}' \(\{email\}\) is being added to your workspace\.\\nThe verification OTP is: \{otp\}\\nIt expires in 5 minutes\.\",\s*settings\.EMAIL_HOST_USER,\s*recipient,\s*fail_silently=True,\s*html_message=f\"\"\"[\s\S]*?\"\"\"\s*\)"

# Note: The add_developer might actually have a slightly varying text and fail_silently=True, I'll match fail_silently=(True|False)... wait
pattern_dev = r"send_mail\(\s*\"Developer Verification OTP - TeamNext\",\s*f\"Hello,\\n\\nA developer \'(?:.*?)\' [\s\S]*?fail_silently=(?:True|False),\s*html_message=f\"\"\"[\s\S]*?\"\"\"\s*\)"

# Use re.sub with a function or just replace.
content = re.sub(pattern_dev, "send_otp_email(recipient, otp, subject='TeamNext Developer Access Verification', context_msg=f\"Request to add developer {name} ({email}) to workspace.\")", content)

# Fallback basic send_mail captures that got left behind
pattern_fallback = r"send_mail\([\s\S]*?fail_silently=False,\s*html_message=f\"\"\"[\s\S]*?\"\"\"\s*\)"
content = re.sub(pattern_fallback, "send_otp_email(email, otp)", content)

with open('myapp/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
