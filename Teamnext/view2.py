import re

with open('myapp/views.py', 'r', encoding='utf-8') as f:
    text = f.read()

pattern = r"send_mail\(\s*\"Developer Verification OTP - TeamNext\",\s*f\"Hello,\\n\\nA developer.*?It expires in 5 minutes\.\",\s*settings\.EMAIL_HOST_USER,\s*recipient,\s*fail_silently=True,\s*html_message=f\"\"\"[\s\S]*?\"\"\"\s*\)"

# Wait, if dd_developer already had html_message, let me check if it did.
# I actually inserted html_message into all ail_silently=False occurrences, but dd_developer had ail_silently=True.
# Let me just show the full text of dd_developer send_mail to make sure I don't guess the regex.
