import re

with open('myapp/views.py', 'r', encoding='utf-8') as f:
    orig = f.read()

# I want to find the whole send_mail in add_developer and replace it.
pattern = re.compile(r"send_mail\([\s\S]*?\"Developer Verification OTP - TeamNext\"[\s\S]*?\)", re.MULTILINE)

replacement = "send_otp_email(recipient, otp, subject='TeamNext Developer Access Verification', context_msg=f'A developer \\'{name}\\' ({email}) is being added to your workspace. Please verify.')"

new_content = pattern.sub(replacement, orig)

with open('myapp/views.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('done replacing add_developer send_mail')
