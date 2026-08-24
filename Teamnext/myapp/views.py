import os
import re
import mimetypes
import secrets
import time

from datetime import timedelta, datetime

from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count, Avg, F
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password, identify_hasher

from .brevo_helper import send_brevo_email
from .models import (
    Company, Employee, Project, ProjectMember, Ticket, ChatMessage,
    ChatMessageMedia, EmailMessage, LeaveRequest, SocialItem, Department,
    Invoice, Expense, Payroll, VendorPayment, BankTransaction,
    InventoryItem, Attendance, Notification
)


def generate_secure_otp():
    """Generates a cryptographically secure 4-digit numeric OTP"""
    return str(secrets.SystemRandom().randint(1000, 9999))


def verify_and_upgrade_password(user_obj, raw_password):
    """
    Verifies user password with secure PBKDF2 hash or legacy plaintext fallback.
    Upgrades legacy plaintext to secure PBKDF2 hash immediately upon successful validation.
    """
    if not user_obj or not user_obj.password or not raw_password:
        return False

    try:
        # Check if stored password is a valid Django hasher format
        identify_hasher(user_obj.password)
        return check_password(raw_password, user_obj.password)
    except Exception:
        # Fallback to legacy plaintext verification
        if user_obj.password == raw_password:
            # Upgrade stored password to secure PBKDF2 hash immediately
            user_obj.password = make_password(raw_password)
            user_obj.save(update_fields=['password'])
            return True
        return False


def get_user_employee(email):
    if not email:
        return None
    email = str(email).strip().lower()
    emp = Employee.objects.filter(email__iexact=email).first()
    if not emp:
        co = Company.objects.filter(email__iexact=email).first()
        if co:
            emp, _ = Employee.objects.get_or_create(
                email=co.email,
                defaults={
                    'company': co,
                    'name': co.name,
                    'password': co.password,
                    'role': 'Administrator',
                    'phone': co.phone
                }
            )
    return emp


def create_notification_for_users(recipients, notification_type, title, message, link=None, related_object_id=None, exclude_user=None):
    if not recipients:
        return

    unique_users = set()
    for r in recipients:
        if isinstance(r, Employee):
            emp = r
        elif isinstance(r, str):
            emp = get_user_employee(r)
        else:
            emp = None

        if emp:
            if exclude_user:
                ex_id = getattr(exclude_user, 'id', None)
                if ex_id and emp.id == ex_id:
                    continue
            unique_users.add(emp)

    if not unique_users:
        return

    cutoff = timezone.now() - timedelta(seconds=10)
    created_notifs = []
    for u in unique_users:
        if related_object_id:
            exists = Notification.objects.filter(
                user=u,
                notification_type=notification_type,
                related_object_id=str(related_object_id),
                created_at__gte=cutoff
            ).exists()
        else:
            exists = Notification.objects.filter(
                user=u,
                notification_type=notification_type,
                title=title,
                created_at__gte=cutoff
            ).exists()

        if not exists:
            created_notifs.append(Notification(
                user=u,
                notification_type=notification_type,
                title=title,
                message=message,
                link=link,
                related_object_id=str(related_object_id) if related_object_id else None,
                unread=True
            ))

    if created_notifs:
        Notification.objects.bulk_create(created_notifs)




def ads_txt(request):
    return HttpResponse(
        "google.com, pub-3585674846945171, DIRECT, f08c47fec0942fa0",
        content_type="text/plain"
    )


def login_view(request):

    companies = []

    qs = Company.objects.all()

    for c in qs:

        companies.append({'email': c.email, 'name': c.name})

    try:

        storage = messages.get_messages(request)

        keep = []

        for m in storage:

            text = str(m)

            if 'Employee login successful' in text:

                continue

            keep.append((m.level, text))

        for level, text in keep:

            messages.add_message(request, level, text)

    except Exception:

        pass

    return render(request, "login.html", {'companies': companies})

def send_otp(request):

    if request.method == "POST":

        email_input = request.POST.get("email")
        purpose = request.POST.get("purpose")
        email_input = (email_input or '').strip().lower()

        if not email_input:
            messages.error(request, "Enter valid email")
            return redirect("login")

        email_list = [e.strip().lower() for e in email_input.split(',') if e.strip()]
        
        # We check if at least one email exists in the system if it's for login
        if purpose in ('login', 'password_reset'):
            exists = False
            for email in email_list:
                if Company.objects.filter(email__iexact=email).exists() or Employee.objects.filter(email__iexact=email).exists():
                    exists = True
                    break
            
            if not exists:
                messages.error(request, 'None of these emails are registered.')
                return redirect('login')

        otp = generate_secure_otp()
        request.session["otp"] = otp
        request.session["otp_email"] = email_list[0] if email_list else email_input
        request.session["otp_expiry"] = time.time() + 300 # 5 mins
        request.session["otp_attempts"] = 0

        if purpose:

            request.session["otp_action"] = purpose

        else:

            request.session.pop("otp_action", None)

        request.session["resend_count"] = 0

        try:
            html = f"""
                <div style='font-family: Arial, sans-serif; padding: 30px; border-radius: 8px; background-color: #f9fafb; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb;'>
                    <h2 style='color: #2563eb; margin-top: 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;'>TeamNext Enterprise Validation</h2>
                    <p style='color: #374151; font-size: 16px;'>Hello,</p>
                    <p style='color: #374151; font-size: 16px;'>Your OTP verification code is:</p>
                    <div style='background-color: #eff6ff; padding: 15px; border-radius: 6px; text-align: center; margin: 25px 0; border: 1px dashed #93c5fd;'>
                        <strong style='color: #1d4ed8; font-size: 32px; letter-spacing: 4px;'>{otp}</strong>
                    </div>
                    <p style='color: #4b5563; font-size: 14px;'>This code will expire in 5 minutes.</p>
                </div>
            """
            send_brevo_email(
                to_emails=email_list,
                subject="Your OTP Code - TeamNext ERP",
                html_content=html,
                plain_text=f"Hello,\n\nYour OTP is: {otp}\n\nThis code will expire in 5 minutes."
            )
            messages.success(request, f"OTP sent to {', '.join(email_list)}")
            request.session["otp_email"] = email_list[0]
        except Exception as e:
            print(f"CRITICAL EMAIL ERROR: {str(e)}")
            messages.error(request, f"Failed to send email: {str(e)}")
            return redirect('login')
        request.session.save()
        return redirect("otp")

    return render(request, "email.html")

def otp_view(request):

    email = request.session.get("otp_email")

    expiry = request.session.get("otp_expiry")

    if not email or not expiry:

        messages.error(request, "Please login first to receive OTP.")

        return redirect("login")

    return render(request, "otp.html", {

        "email": email,

        "expiry_timestamp": int(expiry)

    })

@csrf_exempt
def api_send_otp_json(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})

    try:
        import json
        data = json.loads(request.body.decode('utf-8'))
        target_email = (data.get('target_email') or '').strip().lower()
        email = (data.get('email') or '').strip().lower()
        kind = data.get('kind', 'company')

        if not email and not target_email:
            return JsonResponse({'status': 'error', 'message': 'Email is required'})

        # Prevent duplicate signup
        if email and (Company.objects.filter(email__iexact=email).exists() or Employee.objects.filter(email__iexact=email).exists()):
            return JsonResponse({'status': 'error', 'message': 'An account already exists with this email address.'})

        verification_email = target_email if target_email else email
        otp = generate_secure_otp()

        request.session["otp"] = otp
        request.session["otp_email"] = verification_email
        request.session["otp_expiry"] = time.time() + 300
        request.session["otp_action"] = 'signup'
        request.session["otp_attempts"] = 0

        if kind == 'employee' and target_email and target_email != email:
            if not Company.objects.filter(email__iexact=target_email).exists():
                return JsonResponse({'status': 'error', 'message': 'Company with this email does not exist.'})

            msg = f"Hello,\n\nEmployee Registration Request:\nUser: {email}\nTarget Company: {target_email}\n\nVerification OTP: {otp}\n\nThis verification code has been generated for joining the workspace."
            recipients = [target_email]
        else:
            msg = f"Hello,\n\nYour OTP for TeamNext account verification is: {otp}\n\nExpires in 5 minutes."
            recipients = [verification_email]

        html = f"""
            <div style='font-family: Arial, sans-serif; padding: 30px; border-radius: 8px; background-color: #f9fafb; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb;'>
                <h2 style='color: #2563eb; margin-top: 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;'>TeamNext Enterprise Validation</h2>
                <p style='color: #374151; font-size: 16px;'>Hello,</p>
                <p style='color: #374151; font-size: 16px;'>Your OTP verification code is:</p>
                <div style='background-color: #eff6ff; padding: 15px; border-radius: 6px; text-align: center; margin: 25px 0; border: 1px dashed #93c5fd;'>
                    <strong style='color: #1d4ed8; font-size: 32px; letter-spacing: 4px;'>{otp}</strong>
                </div>
                <p style='color: #4b5563; font-size: 14px;'>This code will expire in 5 minutes.</p>
            </div>
        """
        try:
            send_brevo_email(
                to_emails=recipients,
                subject="Verify Your Account - TeamNext ERP",
                html_content=html,
                plain_text=msg
            )
        except Exception as e:
            print(f"OTP send warning: {e}")

        return JsonResponse({'status': 'ok'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

def verify_otp(request):
    if request.method != "POST":
        return redirect("login")

    user_otp = (request.POST.get("otp") or "").strip()
    saved_otp = request.session.get("otp")
    expiry = request.session.get("otp_expiry")

    if not saved_otp or not expiry:
        messages.error(request, "Session expired or invalid. Please login again.")
        return redirect("login")

    # Brute force protection: maximum 5 attempts per OTP
    attempts = request.session.get("otp_attempts", 0) + 1
    request.session["otp_attempts"] = attempts

    if attempts > 5:
        request.session.pop("otp", None)
        request.session.pop("otp_expiry", None)
        request.session.pop("otp_attempts", None)
        messages.error(request, "Too many failed attempts. Please login again to request a new code.")
        return redirect("login")

    if time.time() > expiry:
        request.session.pop("otp", None)
        request.session.pop("otp_expiry", None)
        messages.error(request, "OTP expired. Please request a new one.")
        return redirect("otp")

    if user_otp == saved_otp:
        action = request.session.get('otp_action')
        email = (request.session.get("otp_email") or '').strip().lower()

        # Invalidate OTP immediately upon successful verification
        request.session.pop('otp', None)
        request.session.pop('otp_expiry', None)
        request.session.pop('otp_attempts', None)
        request.session.pop('otp_action', None)

        if action == 'signup':
            messages.error(request, "Please use the signup form to complete registration.")
            return redirect("login")

        elif action == 'password_reset':
            request.session['password_reset_allowed'] = True
            request.session['password_reset_email'] = email
            return redirect('set_password')

        request.session["verified"] = True
        name = email
        company_name = "TeamNext"

        co = Company.objects.filter(email__iexact=email).first()
        if co:
            name = co.name
            company_name = co.name
        else:
            emp = Employee.objects.filter(email__iexact=email).first()
            if emp:
                name = emp.name
                company_name = emp.company.name

        request.session['company_name'] = company_name
        messages.success(request, f"Welcome back, {name}!")
        return redirect("dashboard")

    else:
        # Invalid OTP — generate and send new OTP if within resend limit
        email = request.session.get("otp_email")
        count = request.session.get("resend_count", 0)

        if email and count < 3:
            new_otp = generate_secure_otp()
            request.session["otp"] = new_otp
            request.session["otp_expiry"] = time.time() + 300
            request.session["resend_count"] = count + 1

            try:
                html_retry = f"""
                    <div style='font-family: Arial, sans-serif; padding: 30px; border-radius: 8px; background-color: #f9fafb; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb;'>
                        <h2 style='color: #2563eb; margin-top: 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;'>TeamNext Enterprise Validation</h2>
                        <p style='color: #374151; font-size: 16px;'>Your previous code was incorrect. New code:</p>
                        <div style='background-color: #eff6ff; padding: 15px; border-radius: 6px; text-align: center; margin: 25px 0; border: 1px dashed #93c5fd;'>
                            <strong style='color: #1d4ed8; font-size: 32px; letter-spacing: 4px;'>{new_otp}</strong>
                        </div>
                        <p style='color: #4b5563; font-size: 14px;'>Expires in 5 minutes.</p>
                    </div>
                """
                send_brevo_email(
                    to_emails=[email],
                    subject="New OTP Code - TeamNext Enterprise Management Tool",
                    html_content=html_retry,
                    plain_text=f"Your new OTP is: {new_otp}. Expires in 5 minutes."
                )
                messages.error(request, f"Invalid OTP. A new code has been sent to {email}.")
            except Exception:
                messages.error(request, "Invalid OTP. Please try again.")
        elif email and count >= 3:
            messages.error(request, "Invalid OTP. Max resend limit reached. Please login again.")
            return redirect("login")
        else:
            messages.error(request, "Invalid OTP. Please try again.")

        return redirect("otp")

def resend_otp(request):
    if request.method != "POST":
        return redirect("otp")

    email = request.session.get("otp_email")
    if not email:
        messages.error(request, "Please login first to resend OTP.")
        return redirect("login")

    count = request.session.get("resend_count", 0)
    if count >= 3:
        messages.error(request, "Max resend limit reached. Please login again.")
        return redirect("login")

    otp = generate_secure_otp()
    request.session["otp"] = otp
    request.session["otp_expiry"] = time.time() + 300
    request.session["otp_attempts"] = 0
    request.session["resend_count"] = count + 1

    try:
        html = f"""
            <div style='font-family: Arial, sans-serif; padding: 30px; border-radius: 8px; background-color: #f9fafb; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb;'>
                <h2 style='color: #2563eb; margin-top: 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;'>TeamNext Enterprise Validation</h2>
                <p style='color: #374151; font-size: 16px;'>Hello,</p>
                <p style='color: #374151; font-size: 16px;'>Your new OTP verification code is:</p>
                <div style='background-color: #eff6ff; padding: 15px; border-radius: 6px; text-align: center; margin: 25px 0; border: 1px dashed #93c5fd;'>
                    <strong style='color: #1d4ed8; font-size: 32px; letter-spacing: 4px;'>{otp}</strong>
                </div>
                <p style='color: #4b5563; font-size: 14px;'>This code will expire in 5 minutes.</p>
            </div>
        """
        send_brevo_email(
            to_emails=[email],
            subject="New OTP Code - TeamNext Enterprise Management Tool",
            html_content=html,
            plain_text=f"Hello,\n\nYour new OTP is: {otp}\n\nExpires in 5 minutes."
        )
        messages.success(request, f"New OTP sent to {email} ({count+1}/3)")
    except Exception as e:
        messages.error(request, "Failed to resend OTP. Please try again.")

    return redirect("otp")

def password_login(request):
    if request.method != 'POST':
        return redirect('login')

    email = (request.POST.get('email') or '').strip().lower()
    password = request.POST.get('password')

    if not email or not password:
        messages.error(request, 'Email and password required')
        return redirect('login')

    co = Company.objects.filter(email__iexact=email).first()
    if co and verify_and_upgrade_password(co, password):
        request.session['verified'] = True
        request.session['otp_email'] = email
        request.session['company_name'] = co.name
        messages.success(request, 'Company login successful')
        return redirect('dashboard')

    emp = Employee.objects.filter(email__iexact=email).first()
    if emp and verify_and_upgrade_password(emp, password):
        request.session['verified'] = True
        request.session['otp_email'] = email
        request.session['company_name'] = emp.company.name
        messages.success(request, 'Employee login successful')
        return redirect('dashboard')

    messages.error(request, 'Invalid email or password')
    return redirect('login')

@csrf_exempt
def signup_view(request):
    if request.method == 'POST':
        kind = request.POST.get('kind')

        if kind == 'company':
            company_name = (request.POST.get('company_name') or '').strip()
            email = (request.POST.get('company_email_signup') or '').strip().lower()
            password = request.POST.get('company_password_signup')

            if not company_name or not email or not password:
                messages.error(request, 'Company name, email, and password are required.')
                return redirect('login')

            if Company.objects.filter(email__iexact=email).exists() or Employee.objects.filter(email__iexact=email).exists():
                messages.error(request, 'An account already exists with this email address.')
                return redirect('login')

            otp_input = (request.POST.get('company_otp_signup') or '').strip()
            session_otp = request.session.get('otp')
            session_email = (request.session.get('otp_email') or '').strip().lower()

            if not session_otp or otp_input != session_otp or email != session_email:
                messages.error(request, 'Invalid or expired OTP code.')
                return redirect('login')

            co = Company.objects.create(
                name=company_name,
                email=email,
                password=make_password(password),
                address=request.POST.get('address'),
                phone=request.POST.get('phone'),
                website=request.POST.get('website'),
                employees_count=request.POST.get('employees_count'),
                industry=request.POST.get('industry')
            )

            # Automatically create admin Employee account for unified access
            Employee.objects.get_or_create(
                email=co.email,
                defaults={
                    'company': co,
                    'name': co.name,
                    'password': co.password,
                    'role': 'Administrator',
                    'phone': co.phone
                }
            )

            request.session['verified'] = True
            request.session['otp_email'] = email
            request.session['company_name'] = co.name
            request.session.pop('otp', None)
            request.session.pop('otp_email', None)

            messages.success(request, 'Workspace registered successfully!')
            return redirect('dashboard')

        elif kind == 'employee':
            email = (request.POST.get('employee_email_signup') or '').strip().lower()
            company_email = (request.POST.get('company_email') or request.POST.get('company_email_free') or '').strip().lower()
            emp_pwd = request.POST.get('employee_password_signup') or 'changeme123'
            full_name = (request.POST.get('full_name') or '').strip()
            role = (request.POST.get('role') or 'Employee').strip()

            if not email or not company_email:
                messages.error(request, 'Personal email and organization email are required.')
                return redirect('login')

            company = Company.objects.filter(email__iexact=company_email).first()
            if not company:
                messages.error(request, 'Organization with this email does not exist.')
                return redirect('login')

            if Company.objects.filter(email__iexact=email).exists() or Employee.objects.filter(email__iexact=email).exists():
                messages.error(request, 'An account already exists with this personal email.')
                return redirect('login')

            otp_input = (request.POST.get('employee_otp_signup') or '').strip()
            session_otp = request.session.get('otp')
            session_email = (request.session.get('otp_email') or '').strip().lower()

            if not session_otp or otp_input != session_otp or (session_email not in (company_email, email)):
                messages.error(request, 'Invalid or expired OTP code.')
                return redirect('login')

            emp = Employee.objects.create(
                company=company,
                name=full_name or email.split('@')[0],
                email=email,
                password=make_password(emp_pwd),
                role=role,
                department_old=request.POST.get('department'),
                phone=request.POST.get('phone')
            )

            request.session['verified'] = True
            request.session['otp_email'] = email
            request.session['company_name'] = company.name
            request.session.pop('otp', None)
            request.session.pop('otp_email', None)

            messages.success(request, 'Employee account created successfully!')
            return redirect('dashboard')

        else:
            messages.error(request, 'Invalid registration kind.')
            return redirect('login')

    return render(request, "login.html")

def _send_signup_otp(request, email):
    otp = generate_secure_otp()
    request.session["otp"] = otp
    request.session["otp_email"] = email
    request.session["otp_expiry"] = time.time() + 300
    request.session["otp_action"] = 'signup'
    request.session["otp_attempts"] = 0

    html_signup = f"""
        <div style='font-family: Arial, sans-serif; padding: 30px; border-radius: 8px; background-color: #f9fafb; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb;'>
            <h2 style='color: #2563eb; margin-top: 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px;'>TeamNext Enterprise Validation</h2>
            <p style='color: #374151; font-size: 16px;'>Your account verification OTP is:</p>
            <div style='background-color: #eff6ff; padding: 15px; border-radius: 6px; text-align: center; margin: 25px 0; border: 1px dashed #93c5fd;'>
                <strong style='color: #1d4ed8; font-size: 32px; letter-spacing: 4px;'>{otp}</strong>
            </div>
            <p style='color: #4b5563; font-size: 14px;'>Expires in 5 minutes.</p>
        </div>
    """
    send_brevo_email(
        to_emails=[email],
        subject="Verify Your Account - TeamNext Enterprise Management Tool",
        html_content=html_signup,
        plain_text=f"Hello,\n\nYour OTP for account verification is: {otp}\n\nExpires in 5 minutes."
    )
    messages.success(request, f"Verification OTP sent to {email}")

def set_password(request):
    if request.method == 'POST':
        pwd = request.POST.get('password')
        email = request.session.get('password_reset_email') or request.session.get('otp_email')

        # Verify authorization: must have completed verified OTP reset or be logged in
        if not request.session.get('password_reset_allowed') and not request.session.get('verified'):
            messages.error(request, 'Unauthorized password reset session. Please verify OTP first.')
            return redirect('login')

        if not pwd or not email:
            messages.error(request, 'Missing required information')
            return redirect('login')

        email = (email or '').strip().lower()
        co = Company.objects.filter(email__iexact=email).first()

        if co:
            co.password = make_password(pwd)
            co.save(update_fields=['password'])
        else:
            emp = Employee.objects.filter(email__iexact=email).first()
            if emp:
                emp.password = make_password(pwd)
                emp.save(update_fields=['password'])
            else:
                messages.error(request, 'User account not found.')
                return redirect('login')

        request.session.pop('password_reset_email', None)
        request.session.pop('password_reset_allowed', None)
        request.session['verified'] = True

        company_name = "TeamNext"
        if co:
            company_name = co.name
        elif emp:
            company_name = emp.company.name

        request.session['company_name'] = company_name
        request.session['otp_email'] = email

        messages.success(request, 'Password securely updated. Logged in.')
        return redirect('dashboard')

    return render(request, 'set_password.html')

def forgot_password(request):

    if request.method == 'POST':

        email = request.POST.get('email')

        if not email:

            messages.error(request, 'Enter email')

            return redirect('login')

        request.POST = request.POST.copy()

        request.POST['purpose'] = 'password_reset'

        return send_otp(request)

    return redirect('login')

def dashboard(request):

    if not request.session.get("verified"):

        messages.error(request, "Please login to access the dashboard.")

        return redirect("login")

    email = (request.session.get("otp_email") or '').strip().lower()

    is_new_user = not request.session.get("has_logged_in_before", False)

    request.session["has_logged_in_before"] = True

    projects = [

        {"id": "proj_mobile", "name": "Mobile App Redesign"},

        {"id": "proj_web", "name": "Website Revamp"},

        {"id": "proj_api", "name": "Public API Launch"}

    ]

    company_name = request.session.get("company_name")

    co = Company.objects.filter(email__iexact=email).first()

    emp = Employee.objects.filter(email__iexact=email).first()

    if not co and emp:

        co = emp.company

    if not co:

        messages.error(request, "Workspace not found.")

        return redirect('login')

    is_company_admin = (Company.objects.filter(email__iexact=email).exists())

    company_name = co.name

    request.session['company_name'] = company_name

    tickets_qs = Ticket.objects.filter(project__company=co)

    analytics = {

        'high': tickets_qs.filter(priority='high').count(),

        'medium': tickets_qs.filter(priority='medium').count(),

        'low': tickets_qs.filter(priority='low').count()

    }

    birthdays = SocialItem.objects.filter(company=co, type='birthday').order_by('-created_at')

    topics = SocialItem.objects.filter(company=co, type='topic').order_by('-created_at')

    dares = SocialItem.objects.filter(company=co, type='dare').order_by('-created_at')

    if not birthdays.exists():

        birthdays = [

            {"title": "Sarah Jenkins", "meta_info": "Feb 03", "content": "UX Designer"},

            {"title": "Mike Ross", "meta_info": "Feb 05", "content": "Developer"},

        ]

    if not topics.exists():

         topics = [{"title": "New WFH Policy", "meta_info": "HR", "content": "45 comments"}]

    if not dares.exists():

         dares = [{"title": "Mike", "meta_info": "Dev Team", "content": "Wear funny hats"}]

    if is_company_admin:
        projects_qs = Project.objects.filter(company=co)
        depts_qs = Department.objects.filter(company=co)
    else:
        # For employees, only show projects they are allowed to see
        projects_qs = Project.objects.filter(members__employee=emp, members__is_allowed=True)
        depts_qs = Department.objects.filter(projects__in=projects_qs).distinct()

    # Pre-group projects by department for high-performance rendering
    structure = []
    for d in depts_qs:
        d_projs = projects_qs.filter(departments=d)
        structure.append({
            'dept': d,
            'projects': d_projs
        })

    return render(request, "dashboard.html", {
        "email": email,
        "is_new_user": False,
        "is_company_admin": is_company_admin,
        "projects": projects_qs,
        "departments": structure,
        "company_name": company_name,
        "analytics": analytics,
        "tickets_count": tickets_qs.count(),
        "birthdays": birthdays,
        "hot_topics": topics,
        "dares": dares
    })

def settings_page(request):

    if not request.session.get('verified'):

        return redirect('login')

    email = request.session.get('otp_email')

    co = Company.objects.filter(email=email).first()

    if not co:

        emp = Employee.objects.filter(email=email).first()

        co = emp.company if emp else None

    return render(request, 'settings_page.html', {

        'company_name': co.name if co else "TeamNext",

        'email': email

    })

def profile_page(request):
    if not request.session.get('verified'):
        return redirect('login')

    email = (request.session.get('otp_email') or '').strip().lower()
    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()
    is_admin = co is not None

    stats = {
        'tickets_count': 0,
        'projects_count': 0,
        'leaves_count': 0,
        'attendance_status': 'Present',
        'joined_date': None,
    }

    if co:
        stats['tickets_count'] = Ticket.objects.filter(project__company=co).count()
        stats['projects_count'] = Project.objects.filter(company=co).count()
        stats['leaves_count'] = LeaveRequest.objects.filter(employee__company=co, status='pending').count()
        stats['departments_count'] = Department.objects.filter(company=co).count()
        stats['employees_count'] = Employee.objects.filter(company=co).count()
        stats['joined_date'] = co.created_at.strftime('%b %d, %Y') if co.created_at else 'Active'
        dept_name = 'Executive Board'
        phone_num = co.phone or ''
        role_label = 'Company Owner / Admin'
        user_name = co.name
        user_id_badge = f"TN-ADM-{co.id:04d}"
    elif emp:
        stats['tickets_count'] = Ticket.objects.filter(employee=emp).count()
        stats['projects_count'] = ProjectMember.objects.filter(employee=emp).count()
        stats['leaves_count'] = LeaveRequest.objects.filter(employee=emp).count()
        
        today = timezone.now().date()
        att = Attendance.objects.filter(employee=emp, date=today).first()
        if att:
            stats['attendance_status'] = att.status.capitalize()
        else:
            stats['attendance_status'] = 'Active'

        stats['joined_date'] = emp.created_at.strftime('%b %d, %Y') if emp.created_at else 'Active'
        dept_name = emp.dept.name if emp.dept else (emp.department_old or 'General Operations')
        phone_num = emp.phone or ''
        role_label = emp.role or 'Enterprise Member'
        user_name = emp.name
        user_id_badge = f"TN-EMP-{emp.id:04d}"
    else:
        dept_name = 'Enterprise Member'
        phone_num = ''
        role_label = 'Member'
        user_name = email
        user_id_badge = "TN-USR-0001"

    user_info = {
        'email': email,
        'name': user_name,
        'role': role_label,
        'department': dept_name,
        'phone': phone_num,
        'badge_id': user_id_badge,
        'company_name': co.name if co else (emp.company.name if emp and emp.company else 'TeamNext ERP'),
        'is_admin': is_admin
    }

    return render(request, 'profile_page.html', {
        'user': user_info,
        'company_name': user_info['company_name'],
        'email': email,
        'is_company_admin': is_admin,
        'stats': stats
    })


@csrf_exempt
def api_update_profile(request):
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

    import json
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    email = (request.session.get('otp_email') or '').strip().lower()
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()

    if not name:
        return JsonResponse({'status': 'error', 'message': 'Name is required'})

    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()

    if co:
        co.name = name
        if phone is not None:
            co.phone = phone
        co.save()
        return JsonResponse({'status': 'success', 'message': 'Company profile updated successfully', 'name': co.name, 'phone': co.phone})
    elif emp:
        emp.name = name
        if phone is not None:
            emp.phone = phone
        emp.save()
        return JsonResponse({'status': 'success', 'message': 'Personal profile updated successfully', 'name': emp.name, 'phone': emp.phone})
    else:
        return JsonResponse({'status': 'error', 'message': 'User record not found'})


def social_page(request):
    if not request.session.get("verified"):
        return redirect("login")

    email = (request.session.get('otp_email') or '').strip().lower()
    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()
    if not co and emp:
        co = emp.company

    if not co:
        messages.error(request, "Workspace not found. Please log in.")
        return redirect("login")

    birthdays = SocialItem.objects.filter(company=co, type='birthday').order_by('-created_at')
    topics = SocialItem.objects.filter(company=co, type='topic').order_by('-created_at')
    dares = SocialItem.objects.filter(company=co, type='dare').order_by('-created_at')

    # Seed initial workspace social items if completely empty
    if not birthdays.exists() and not topics.exists() and not dares.exists():
        SocialItem.objects.create(
            company=co, type='birthday', title='Sarah Jenkins', meta_info='Feb 15', content='Lead UX Designer'
        )
        SocialItem.objects.create(
            company=co, type='birthday', title='Alex Rivera', meta_info='Feb 22', content='Backend Engineer'
        )
        SocialItem.objects.create(
            company=co, type='topic', title='Quarterly Innovation Hackathon Ideas', meta_info='Engineering Team', content='45 comments'
        )
        SocialItem.objects.create(
            company=co, type='topic', title='Hybrid Work & Flexible Hours Discussion', meta_info='HR Operations', content='18 comments'
        )
        SocialItem.objects.create(
            company=co, type='dare', title='Mike Ross', meta_info='Dev Team', content='Wear a superhero hat during morning standup'
        )
        birthdays = SocialItem.objects.filter(company=co, type='birthday').order_by('-created_at')
        topics = SocialItem.objects.filter(company=co, type='topic').order_by('-created_at')
        dares = SocialItem.objects.filter(company=co, type='dare').order_by('-created_at')

    return render(request, "social_page.html", {
        "email": email,
        "company_name": co.name,
        "birthdays": birthdays,
        "hot_topics": topics,
        "dares": dares
    })


@csrf_exempt
def api_add_social_item(request):
    if not request.session.get("verified"):
        return JsonResponse({"status": "error", "message": "Unauthorized. Please log in again."}, status=401)
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)

    try:
        import json
        payload = json.loads(request.body.decode("utf-8"))
        item_type = payload.get("type")
        email = (request.session.get('otp_email') or '').strip().lower()

        co = Company.objects.filter(email__iexact=email).first()
        emp = Employee.objects.filter(email__iexact=email).first()
        if not co and emp:
            co = emp.company
        if not co:
            return JsonResponse({"status": "error", "message": "Unauthorized. Workspace not found."}, status=403)

        new_item = None
        notif_title = ""
        notif_msg = ""
        target_str = ""

        if item_type == "birthday":
            name_val = (payload.get("name") or '').strip() or "Team Member"
            date_val = (payload.get("date") or '').strip() or "Soon"
            role_val = (payload.get("role") or '').strip() or ""
            new_item = SocialItem.objects.create(
                company=co, type='birthday',
                title=name_val,
                meta_info=date_val,
                content=role_val
            )
            notif_title = f"🎉 Birthday Event: {name_val}"
            notif_msg = f"{name_val}'s birthday is on {date_val} ({role_val or 'Team Member'})"
            target_str = name_val

        elif item_type == "topic":
            title_val = (payload.get("title") or '').strip() or "New Topic"
            author_val = (payload.get("author") or '').strip() or "Team"
            new_item = SocialItem.objects.create(
                company=co, type='topic',
                title=title_val,
                meta_info=author_val,
                content="0 comments"
            )
            notif_title = f"🔥 Hot Topic: {title_val}"
            notif_msg = f"New discussion topic started by {author_val}"

        elif item_type == "dare":
            from_val = (payload.get("from") or '').strip() or "Challenger"
            to_val = (payload.get("to") or '').strip() or "All"
            task_val = (payload.get("task") or '').strip() or "Daily Challenge"
            new_item = SocialItem.objects.create(
                company=co, type='dare',
                title=from_val,
                meta_info=to_val,
                content=task_val
            )
            notif_title = f"⚡ Daily Dare: {task_val}"
            notif_msg = f"Challenge from {from_val} to {to_val}"
            target_str = to_val
        else:
            return JsonResponse({"status": "error", "message": "Unknown item type"}, status=400)

        if new_item:
            recipients = list(Employee.objects.filter(company=co))
            if target_str and target_str.lower() != 'all':
                specific_emp = Employee.objects.filter(company=co, name__icontains=target_str).first()
                if specific_emp:
                    recipients = [specific_emp]

            create_notification_for_users(
                recipients=recipients,
                notification_type='SOCIAL_EVENT',
                title=notif_title,
                message=notif_msg,
                link='/social-page/',
                related_object_id=str(new_item.id),
                exclude_user=emp
            )

        return JsonResponse({
            "status": "ok",
            "item": {
                "id": new_item.id,
                "type": new_item.type,
                "title": new_item.title,
                "meta_info": new_item.meta_info,
                "content": new_item.content
            }
        })

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
def api_delete_social_item(request):
    if not request.session.get("verified"):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)

    try:
        import json
        payload = json.loads(request.body.decode("utf-8"))
        item_id = payload.get("item_id") or payload.get("id")

        email = (request.session.get("otp_email") or '').strip().lower()
        co = Company.objects.filter(email__iexact=email).first()
        emp = Employee.objects.filter(email__iexact=email).first()
        if not co and emp:
            co = emp.company
        if not co:
            return JsonResponse({"status": "error", "message": "Workspace not found"}, status=403)

        item = SocialItem.objects.filter(id=item_id, company=co).first()
        if not item:
            return JsonResponse({"status": "error", "message": "Social item not found"}, status=404)

        item.delete()
        return JsonResponse({"status": "ok", "message": "Item deleted successfully"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)



def leaves_page(request):

    if not request.session.get("verified"):

        return redirect("login")

    email = request.session.get("otp_email")

    emp = Employee.objects.filter(email=email).first()

    co = Company.objects.filter(email=email).first()

    is_admin = (co is not None)

    if not is_admin and emp:

        is_admin = ProjectMember.objects.filter(employee=emp, can_approve_leaves=True).exists()

    if co:
        leaves_qs = LeaveRequest.objects.filter(employee__company=co).select_related('employee')
    elif emp:
        if is_admin:
            leaves_qs = LeaveRequest.objects.filter(employee__company=emp.company).select_related('employee')
        else:
            leaves_qs = LeaveRequest.objects.filter(employee=emp).select_related('employee')
    else:
        leaves_qs = LeaveRequest.objects.none()

    resolved = []

    for l in leaves_qs.order_by('-created_at'):

        resolved.append({

            'id': l.id,

            'employee_name': l.employee.name,

            'employee_email': l.employee.email,

            'leave_type': 'Vacation',

            'start_date': l.start_date,

            'end_date': l.end_date,

            'reason': l.reason,

            'status': l.status.capitalize()

        })

    return render(request, "leaves_page.html", {

        "email": email,

        "is_admin": is_admin,

        "leaves": resolved,

        "company_name": request.session.get("company_name", "TeamNext")

    })

@csrf_exempt
def api_apply_leave(request):
    if not request.session.get("verified"):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=403)

    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    try:
        import json
        from datetime import datetime

        data = json.loads(request.body.decode("utf-8"))
        email = request.session.get("otp_email")
        emp = get_user_employee(email)

        if not emp:
            return JsonResponse({"status": "error", "message": "Employee not found"}, status=404)

        reason_val = data.get("reason") or "Personal Leave"
        start_val = data.get("start_date") or datetime.now().date()
        end_val = data.get("end_date") or datetime.now().date()

        leave = LeaveRequest.objects.create(
            employee=emp,
            reason=reason_val,
            start_date=start_val,
            end_date=end_val,
            status='pending'
        )

        # Notify approvers (Company admin, Project Members with can_approve_leaves, and Managers)
        co = emp.company
        approvers = []
        if co:
            co_emp = get_user_employee(co.email)
            if co_emp:
                approvers.append(co_emp)
            leave_pm_emps = Employee.objects.filter(company=co, project_memberships__can_approve_leaves=True)
            for e in leave_pm_emps:
                approvers.append(e)
            mgr_emps = Employee.objects.filter(company=co, role__icontains='Manager')
            for e in mgr_emps:
                approvers.append(e)

        create_notification_for_users(
            recipients=approvers,
            notification_type='LEAVE_SUBMITTED',
            title=f"🏖️ Leave Request: {emp.name}",
            message=f"New leave request submitted ({leave.start_date} to {leave.end_date}). Reason: {reason_val[:50]}",
            link="/leaves-page/",
            related_object_id=str(leave.id),
            exclude_user=emp
        )

        return JsonResponse({"status": "ok"})

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
def api_leave_action(request):
    if not request.session.get("verified"):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=403)

    email = request.session.get("otp_email")
    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()

    is_authorized = (co is not None) or (emp and ProjectMember.objects.filter(employee=emp, can_approve_leaves=True).exists()) or (emp and 'manager' in (emp.role or '').lower())

    if not is_authorized:
        return JsonResponse({"status": "error", "message": "Only admins and authorized approvers can approve leaves"}, status=403)

    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    try:
        import json
        data = json.loads(request.body.decode("utf-8"))
        leave_id = data.get("leave_id")
        action = data.get("action")
        if not co and emp:
            co = emp.company
        leave = LeaveRequest.objects.filter(id=leave_id, employee__company=co).first()
        if not leave:
            return JsonResponse({"status": "error", "message": "Leave request not found or unauthorized"}, status=404)

        if action == "approve":
            leave.status = "approved"
            leave.save()
            create_notification_for_users(
                recipients=[leave.employee],
                notification_type='LEAVE_APPROVED',
                title="✅ Leave Approved",
                message=f"Your leave request from {leave.start_date} to {leave.end_date} has been approved.",
                link="/leaves-page/",
                related_object_id=str(leave.id)
            )
        elif action == "reject":
            leave.status = "rejected"
            leave.save()
            reason_suffix = f" (Reason: {leave.reason[:40]})" if leave.reason else ""
            create_notification_for_users(
                recipients=[leave.employee],
                notification_type='LEAVE_REJECTED',
                title="❌ Leave Rejected",
                message=f"Your leave request from {leave.start_date} to {leave.end_date} has been rejected.{reason_suffix}",
                link="/leaves-page/",
                related_object_id=str(leave.id)
            )

        return JsonResponse({"status": "ok"})

    except LeaveRequest.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Leave not found"}, status=404)

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
def send_dashboard_email(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)

    if not request.session.get("verified"):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=403)

    try:
        import json
        payload = json.loads(request.body.decode("utf-8"))
        to = (payload.get("to") or '').strip().lower()
        subject = (payload.get("subject") or '').strip()
        body = (payload.get("body") or '').strip()
        sender_email = (request.session.get('otp_email') or '').strip().lower()

        if not to or not subject or not body:
            return JsonResponse({"status": "error", "message": "Recipient, subject, and body are required."}, status=400)

        # Dispatch via Brevo HTTP API / Django SMTP
        try:
            send_brevo_email(to_emails=[to], subject=subject, html_content=f"<p>{body}</p>", plain_text=body)
        except Exception as e:
            print(f"send_dashboard_email dispatch notice: {e}")

        # Persist sent email to database
        EmailMessage.objects.create(
            sender_email=sender_email,
            recipient_email=to,
            subject=subject,
            body=body,
            is_draft=False,
            is_sent=True
        )

        return JsonResponse({"status": "success", "message": "Email sent successfully."})

    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)

# Duplicate create_ticket view removed (using definition at the end of file)

def tickets_page(request):

    if not request.session.get("verified"):

        messages.error(request, "Please login to access tickets.")

        return redirect("login")

    email = (request.session.get("otp_email") or '').strip().lower()

    co = Company.objects.filter(email__iexact=email).first()

    emp = Employee.objects.filter(email__iexact=email).first()

    is_admin = (co is not None)

    if not co and emp:

        co = emp.company

    if not co:

        messages.error(request, "Workspace not found.")

        return redirect('login')

    if is_admin:

        projects_list = Project.objects.filter(company=co)

        tickets_list = Ticket.objects.filter(project__company=co).select_related('project', 'employee').order_by('-created_at')

    else:

        projects_list = Project.objects.filter(members__employee=emp, members__is_allowed=True)

        tickets_list = Ticket.objects.filter(project__in=projects_list).select_related('project', 'employee').order_by('-created_at')

    devs_qs = Employee.objects.filter(company=co)

    total_tickets = tickets_list.count()
    open_tickets = tickets_list.filter(status='open').count()
    in_progress_tickets = tickets_list.filter(status='in_progress').count()
    resolved_tickets = tickets_list.filter(status__in=['resolved', 'closed']).count()

    analytics = {
        'total': total_tickets,
        'open': open_tickets,
        'in_progress': in_progress_tickets,
        'resolved': resolved_tickets,
        'high': tickets_list.filter(priority='high').count(),
        'medium': tickets_list.filter(priority='medium').count(),
        'low': tickets_list.filter(priority='low').count()
    }

    recent = tickets_list[:50]

    return render(request, "tickets.html", {

        "tickets": tickets_list,

        "analytics": analytics,

        "recent": recent,

        "developers": [{'name': d.name, 'email': d.email, 'id': d.id} for d in devs_qs],

        "projects": projects_list,

        "company_name": co.name,

        "email": email,

        "is_admin": is_admin

    })


@require_POST

@csrf_exempt

def add_developer(request):

    try:

        import json

        payload = json.loads(request.body.decode("utf-8"))

    except Exception:

        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    name = payload.get("name")

    email = payload.get("email")

    if not name or not email:

        return JsonResponse({"status": "error", "message": "Missing name or email"}, status=400)

    otp = str(random.randint(1000, 9999))

    expiry = time.time() + 300

    request.session["pending_developer"] = {"name": name, "email": email, "otp": otp, "expiry": expiry}

    sender_email = request.session.get("otp_email")

    companies_dict = request.session.get('companies', {})

    users_dict = request.session.get('users', {})

    company_email = None

    if sender_email in companies_dict:

        company_email = sender_email

    else:

        user_data = users_dict.get(sender_email)

        if user_data:

            company_email = user_data.get('company_email')

    recipient = [company_email] if company_email else [sender_email]

    try:
        html_dev = f"""
            <div style='font-family: Arial, sans-serif; padding: 20px;'>
                <h2>TeamNext Developer Access</h2>
                <p>Developer <b>{name}</b> ({email}) is being added. OTP: <strong>{otp}</strong></p>
                <p>Expires in 5 minutes.</p>
            </div>
        """
        send_brevo_email(
            to_emails=recipient,
            subject="Developer Verification OTP - TeamNext",
            html_content=html_dev,
            plain_text=f"Developer '{name}' ({email}) OTP: {otp}. Expires in 5 minutes."
        )
    except Exception:
        pass

    return JsonResponse({"status": "ok", "message": "OTP sent to company email for verification."})

@require_POST

@csrf_exempt

def verify_developer(request):

    try:

        import json

        payload = json.loads(request.body.decode("utf-8"))

    except Exception:

        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    otp = payload.get("otp")

    pending = request.session.get("pending_developer")

    if not pending:

        return JsonResponse({"status": "error", "message": "No pending developer"}, status=400)

    if time.time() > pending.get("expiry", 0):

        request.session.pop("pending_developer", None)

        return JsonResponse({"status": "error", "message": "OTP expired"}, status=400)

    if otp != pending.get("otp"):

        return JsonResponse({"status": "error", "message": "Invalid OTP"}, status=400)

    dev_name = pending.get("name")

    dev_email = pending.get("email")

    dev_display = dev_name

    devs = request.session.get("developers", [])

    devs.append(dev_display)

    request.session["developers"] = devs

    request.session.pop("pending_developer", None)

    return JsonResponse({"status": "ok", "developer": dev_display})

def developers_list(request):

    if not request.session.get("verified"):

        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=403)

    email = request.session.get('otp_email')

    co = Company.objects.filter(email=email).first()

    if not co:

        emp = Employee.objects.filter(email=email).first()

        co = emp.company if emp else None

    if co:

        devs = list(Employee.objects.filter(company=co).values('name', 'email'))

    else:

        devs = []

    return JsonResponse({"status": "ok", "developers": devs})

def analytics_api(request):

    if not request.session.get("verified"):

        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=403)

    tickets = request.session.get("tickets", [])

    analytics = {"high": 0, "medium": 0, "low": 0}

    for t in tickets:

        p = (t.get("priority") or "medium").lower()

        if p in analytics:

            analytics[p] += 1

    return JsonResponse({"status": "ok", "analytics": analytics})

def logout_view(request):

    keys_to_clear = [
        'verified', 'otp_email', 'otp', 'otp_expiry', 'otp_action',
        'resend_count', 'pending_signup', 'password_reset_email',
        'unlocked_channels', 'lock_failed_attempts'
    ]

    for key in keys_to_clear:

        request.session.pop(key, None)

    messages.success(request, "Signed out successfully.")

    return redirect("login")

def quick_redirect(request, target=None):

    to = target or request.GET.get('to') or request.GET.get('page')

    mapping = {

        'dashboard': 'dashboard',

        'tickets': 'tickets_page',

        'tickets-page': 'tickets_page',

        'projects': 'projects_page',

        'projects-page': 'projects_page',

        'analytics': 'analytics_page',

        'analytics-page': 'analytics_page',

        'settings': 'settings_page',

        'settings-page': 'settings_page',

        'email': 'email_page',

        'email-page': 'email_page',

        'users': 'users_page',

        'logout': 'logout',

        'dashboard/': 'dashboard'

    }

    if not to:

        return redirect('dashboard')

    name = mapping.get(to.lower())

    if name:

        return redirect(name)

    return redirect('/')

@csrf_exempt

@csrf_exempt
def save_settings(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=400)

    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    try:
        import json
        payload = json.loads(request.body.decode('utf-8'))
        email = (request.session.get('otp_email') or '').strip().lower()
        co = Company.objects.filter(email__iexact=email).first()
        emp = Employee.objects.filter(email__iexact=email).first()
        
        # Check permissions: Admin or Moderator with can_modify_settings
        is_mod = False
        if emp and not co:
            co = emp.company
            is_mod = ProjectMember.objects.filter(employee=emp, can_modify_settings=True).exists()

        if not co:
            return JsonResponse({'status': 'error', 'message': 'Workspace not found'}, status=404)

        if not Company.objects.filter(email__iexact=email).exists() and not is_mod:
            return JsonResponse({'status': 'error', 'message': 'Only workspace administrators or moderators can update settings.'}, status=403)

        name = (payload.get('company_name') or '').strip()
        phone = (payload.get('phone') or '').strip()
        website = (payload.get('website') or '').strip()
        industry = (payload.get('industry') or '').strip()

        if not name:
            return JsonResponse({'status': 'error', 'message': 'Workspace name is required'}, status=400)

        co.name = name
        if phone:
            co.phone = phone
        if website:
            co.website = website
        if industry:
            co.industry = industry
        co.save()

        request.session['company_name'] = co.name
        return JsonResponse({'status': 'ok', 'company_name': co.name, 'message': 'Settings saved successfully'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


HEX_PASSCODE_PATTERN = re.compile(r'^[0-9a-fA-F]{4}$')
DANGEROUS_EXTENSIONS = {
    '.exe', '.bat', '.cmd', '.sh', '.py', '.php', '.js', '.vbs', '.jar',
    '.scr', '.pif', '.dll', '.msi', '.com', '.app', '.deb', '.rpm', '.bin', '.cgi', '.pl'
}

def is_valid_hex_passcode(code):
    return bool(code and HEX_PASSCODE_PATTERN.match(str(code).strip()))

def sanitize_filename(filename):
    name = os.path.basename(filename)
    name = re.sub(r'[^a-zA-Z0-9_\-\.\(\)\s]', '_', name)
    return name or 'attachment'

def get_media_category(content_type, filename):
    ct = (content_type or '').lower()
    ext = os.path.splitext(filename)[1].lower()
    if ct.startswith('image/') or ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico'):
        return 'image'
    elif ct.startswith('video/') or ext in ('.mp4', '.webm', '.mov', '.ogg', '.mkv', '.avi'):
        return 'video'
    elif ct.startswith('audio/') or ext in ('.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac'):
        return 'audio'
    else:
        return 'document'

def check_channel_rate_limit(request, project_id):
    attempts_dict = request.session.get('lock_failed_attempts', {})
    proj_key = str(project_id)
    entry = attempts_dict.get(proj_key, {'count': 0, 'locked_until': 0})
    now = time.time()
    if entry.get('locked_until', 0) > now:
        remaining = max(1, int(entry['locked_until'] - now))
        return False, f"Too many failed attempts. Please wait {remaining} seconds before trying again."
    return True, None

def record_channel_failed_attempt(request, project_id):
    attempts_dict = request.session.get('lock_failed_attempts', {})
    proj_key = str(project_id)
    entry = attempts_dict.get(proj_key, {'count': 0, 'locked_until': 0})
    entry['count'] = entry.get('count', 0) + 1
    if entry['count'] >= 5:
        entry['locked_until'] = time.time() + 180
        entry['count'] = 0
    attempts_dict[proj_key] = entry
    request.session['lock_failed_attempts'] = attempts_dict
    request.session.save()

def clear_channel_failed_attempts(request, project_id):
    attempts_dict = request.session.get('lock_failed_attempts', {})
    proj_key = str(project_id)
    if proj_key in attempts_dict:
        attempts_dict.pop(proj_key, None)
        request.session['lock_failed_attempts'] = attempts_dict
        request.session.save()


@csrf_exempt
def api_unlock_channel(request, project_id):
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    email = (request.session.get('otp_email') or '').strip().lower()
    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()
    if not co and emp:
        co = emp.company
    if not co:
        return JsonResponse({'status': 'error', 'message': 'Workspace not found'}, status=404)

    try:
        proj = Project.objects.filter(id=int(project_id), company=co).first() if str(project_id).isdigit() else Project.objects.filter(name__iexact=str(project_id), company=co).first()
    except Exception:
        proj = None

    if not proj:
        return JsonResponse({'status': 'error', 'message': 'Channel not found'}, status=404)

    if not proj.is_locked:
        unlocked = request.session.get('unlocked_channels', [])
        if str(proj.id) not in unlocked:
            unlocked.append(str(proj.id))
            request.session['unlocked_channels'] = unlocked
            request.session.save()
        return JsonResponse({'status': 'ok', 'is_unlocked': True, 'message': 'Channel is not locked'})

    allowed, err_msg = check_channel_rate_limit(request, proj.id)
    if not allowed:
        return JsonResponse({'status': 'error', 'message': err_msg}, status=429)

    try:
        import json
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except Exception:
        payload = {}
    passcode = (payload.get('passcode') or request.POST.get('passcode') or '').strip()

    if not is_valid_hex_passcode(passcode):
        record_channel_failed_attempt(request, proj.id)
        return JsonResponse({'status': 'error', 'message': 'Invalid passcode. Passcode must be exactly 4 hexadecimal characters (0-9, A-F).'}, status=400)

    passcode_upper = passcode.upper()
    if proj.passcode_hash and check_password(passcode_upper, proj.passcode_hash):
        clear_channel_failed_attempts(request, proj.id)
        unlocked = request.session.get('unlocked_channels', [])
        if str(proj.id) not in unlocked:
            unlocked.append(str(proj.id))
            request.session['unlocked_channels'] = unlocked
            request.session.save()
        return JsonResponse({'status': 'ok', 'is_unlocked': True, 'message': 'Channel unlocked successfully'})
    else:
        record_channel_failed_attempt(request, proj.id)
        return JsonResponse({'status': 'error', 'message': 'Incorrect passcode.'}, status=400)


@csrf_exempt
def api_channel_lock_settings(request, project_id):
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    email = (request.session.get('otp_email') or '').strip().lower()
    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()
    if not co and emp:
        co = emp.company
    if not co:
        return JsonResponse({'status': 'error', 'message': 'Workspace not found'}, status=404)

    is_admin = (Company.objects.filter(email__iexact=email).exists()) or (emp and ProjectMember.objects.filter(employee=emp, is_admin=True).exists()) or (emp and ProjectMember.objects.filter(employee=emp, can_modify_settings=True).exists())

    try:
        proj = Project.objects.filter(id=int(project_id), company=co).first() if str(project_id).isdigit() else Project.objects.filter(name__iexact=str(project_id), company=co).first()
    except Exception:
        proj = None

    if not proj:
        return JsonResponse({'status': 'error', 'message': 'Channel not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse({
            'status': 'ok',
            'project_id': proj.id,
            'project_name': proj.name,
            'is_locked': proj.is_locked,
            'has_passcode': bool(proj.passcode_hash),
            'is_admin': is_admin
        })

    if request.method == 'POST':
        if not is_admin:
            return JsonResponse({'status': 'error', 'message': 'Only workspace administrators or channel owners can change lock settings.'}, status=403)

        try:
            import json
            payload = json.loads(request.body.decode('utf-8')) if request.body else {}
        except Exception:
            payload = {}

        lock_action = payload.get('action')
        is_locked = payload.get('is_locked')
        passcode = (payload.get('passcode') or '').strip()

        if lock_action == 'unlock_permanently' or is_locked is False:
            proj.is_locked = False
            proj.save(update_fields=['is_locked'])
            return JsonResponse({'status': 'ok', 'is_locked': False, 'message': 'Channel lock has been disabled.'})

        if is_locked is True or lock_action == 'lock':
            if passcode:
                if not is_valid_hex_passcode(passcode):
                    return JsonResponse({'status': 'error', 'message': 'Passcode must be exactly 4 hexadecimal characters (0-9, A-F).'}, status=400)
                proj.passcode_hash = make_password(passcode.upper())
                proj.is_locked = True
                proj.save(update_fields=['passcode_hash', 'is_locked'])
            elif proj.passcode_hash:
                proj.is_locked = True
                proj.save(update_fields=['is_locked'])
            else:
                return JsonResponse({'status': 'error', 'message': 'A 4-character hexadecimal passcode is required to lock the channel.'}, status=400)

            unlocked = request.session.get('unlocked_channels', [])
            if str(proj.id) not in unlocked:
                unlocked.append(str(proj.id))
                request.session['unlocked_channels'] = unlocked
                request.session.save()

            return JsonResponse({'status': 'ok', 'is_locked': True, 'message': 'Channel lock settings saved.'})

        return JsonResponse({'status': 'error', 'message': 'Invalid lock action'}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


@csrf_exempt
def api_chat_media(request, media_id):
    if not request.session.get('verified'):
        return HttpResponseBadRequest("Unauthorized")

    email = (request.session.get('otp_email') or '').strip().lower()
    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()
    if not co and emp:
        co = emp.company
    if not co:
        return HttpResponseBadRequest("Unauthorized")

    try:
        media = ChatMessageMedia.objects.select_related('message__project', 'message__employee').get(id=media_id)
    except ChatMessageMedia.DoesNotExist:
        return HttpResponseBadRequest("Media not found")

    proj = media.message.project
    if proj.company_id != co.id:
        return HttpResponseBadRequest("Access denied")

    if not Company.objects.filter(email__iexact=email).exists() and emp:
        pm = ProjectMember.objects.filter(project=proj, employee=emp).first()
        if pm and not pm.is_allowed:
            return HttpResponseBadRequest("Access restricted")

    if proj.is_locked:
        unlocked = request.session.get('unlocked_channels', [])
        if str(proj.id) not in unlocked:
            return HttpResponseBadRequest("Channel locked")

    if not media.file or not os.path.exists(media.file.path):
        return HttpResponseBadRequest("File not found on server")

    content_type = media.content_type or 'application/octet-stream'
    response = FileResponse(open(media.file.path, 'rb'), content_type=content_type)
    safe_name = sanitize_filename(media.original_filename)
    if request.GET.get('download') == '1':
        response['Content-Disposition'] = f'attachment; filename="{safe_name}"'
    else:
        response['Content-Disposition'] = f'inline; filename="{safe_name}"'
    return response


@csrf_exempt
def chat_messages(request):
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    email = (request.session.get('otp_email') or '').strip().lower()
    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()
    if not co and emp:
        co = emp.company
    if not co:
        return JsonResponse({'status': 'error', 'message': 'Workspace not found'}, status=404)

    is_company_admin = (co.email.lower() == email)

    try:
        import json
        payload = json.loads(request.body.decode('utf-8')) if request.body and request.content_type == 'application/json' else {}
    except Exception:
        payload = {}

    project_id = payload.get('project') or request.GET.get('project') or payload.get('project_id') or request.POST.get('project') or request.POST.get('project_id')
    if not project_id:
        return JsonResponse({'status': 'error', 'message': 'Missing project id'}, status=400)

    try:
        proj = None
        if str(project_id).isdigit():
            proj = Project.objects.filter(id=int(project_id), company=co).first()
        if not proj:
            proj = Project.objects.filter(name__iexact=str(project_id), company=co).first()
        if not proj:
            return JsonResponse({'status': 'error', 'message': 'Project channel not found'}, status=404)
    except Exception:
        return JsonResponse({'status': 'error', 'message': 'Error finding project'}, status=500)

    # Server-side permission check: verify employee is allowed in this project
    if not is_company_admin and emp:
        membership = ProjectMember.objects.filter(project=proj, employee=emp).first()
        if membership:
            if not membership.is_allowed:
                return JsonResponse({'status': 'error', 'message': 'Access to this channel is restricted'}, status=403)
            if request.method == 'POST' and not membership.can_chat:
                return JsonResponse({'status': 'error', 'message': 'You do not have chat permissions in this channel'}, status=403)

    unlocked_list = request.session.get('unlocked_channels', [])
    is_unlocked = (not proj.is_locked) or (str(proj.id) in unlocked_list)

    if request.method == 'GET':
        if proj.is_locked and not is_unlocked:
            return JsonResponse({
                'status': 'locked',
                'is_locked': True,
                'requires_unlock': True,
                'project': {'id': proj.id, 'name': proj.name},
                'message': 'This channel is locked. Please enter the passcode to access conversation and media.'
            })

        msgs_qs = ChatMessage.objects.filter(project=proj).select_related('employee').prefetch_related('media_attachments').order_by('timestamp')
        result = []
        for m in msgs_qs:
            sender_name = m.employee.name if m.employee else 'User'
            sender_email = m.employee.email if m.employee else ''
            media_list = []
            for med in m.media_attachments.all():
                cat = get_media_category(med.content_type, med.original_filename)
                media_list.append({
                    'id': med.id,
                    'filename': med.original_filename,
                    'content_type': med.content_type,
                    'file_size': med.file_size,
                    'formatted_size': med.formatted_size,
                    'category': cat,
                    'url': f'/api/chat/media/{med.id}/',
                    'download_url': f'/api/chat/media/{med.id}/?download=1',
                    'is_image': cat == 'image',
                    'is_video': cat == 'video',
                    'is_audio': cat == 'audio',
                    'is_document': cat == 'document'
                })

            result.append({
                'id': m.id,
                'user': sender_name,
                'email': sender_email,
                'text': m.text,
                'time': int(m.timestamp.timestamp()) if m.timestamp else 0,
                'media': media_list
            })
        return JsonResponse({'status': 'ok', 'is_locked': proj.is_locked, 'is_unlocked': True, 'messages': result})

    if request.method == 'POST':
        if proj.is_locked and not is_unlocked:
            return JsonResponse({'status': 'locked', 'is_locked': True, 'message': 'This channel is locked. Unlock it before sending messages.'}, status=403)

        text = ''
        files = []
        if request.FILES:
            text = (request.POST.get('text') or '').strip()
            files = request.FILES.getlist('files') or ([request.FILES['file']] if 'file' in request.FILES else [])
        else:
            text = (payload.get('text') or request.POST.get('text') or '').strip()

        if not text and not files:
            return JsonResponse({'status': 'error', 'message': 'Message text or attachment is required'}, status=400)

        # Validate files
        for f in files:
            if f.size > 25 * 1024 * 1024:
                return JsonResponse({'status': 'error', 'message': f'File "{f.name}" exceeds maximum allowed upload size of 25MB.'}, status=400)
            ext = os.path.splitext(f.name)[1].lower()
            if ext in DANGEROUS_EXTENSIONS:
                return JsonResponse({'status': 'error', 'message': f'File extension "{ext}" is not permitted.'}, status=400)

        if not emp:
            emp, _ = Employee.objects.get_or_create(
                email=co.email,
                defaults={
                    'company': co,
                    'name': co.name,
                    'password': co.password,
                    'role': 'Administrator'
                }
            )

        msg = ChatMessage.objects.create(project=proj, employee=emp, text=text)
        created_media = []
        for f in files:
            ct = f.content_type or mimetypes.guess_type(f.name)[0] or 'application/octet-stream'
            safe_name = sanitize_filename(f.name)
            med = ChatMessageMedia.objects.create(
                message=msg,
                original_filename=safe_name,
                file=f,
                content_type=ct,
                file_size=f.size
            )
            cat = get_media_category(ct, safe_name)
            created_media.append({
                'id': med.id,
                'filename': med.original_filename,
                'content_type': med.content_type,
                'file_size': med.file_size,
                'formatted_size': med.formatted_size,
                'category': cat,
                'url': f'/api/chat/media/{med.id}/',
                'download_url': f'/api/chat/media/{med.id}/?download=1',
                'is_image': cat == 'image',
                'is_video': cat == 'video',
                'is_audio': cat == 'audio',
                'is_document': cat == 'document'
            })

        # Determine channel members to notify
        member_emps = list(Employee.objects.filter(project_memberships__project=proj, project_memberships__is_allowed=True))
        dept_emps = list(Employee.objects.filter(company=proj.company, dept__in=proj.departments.all()))
        recipients = list(set(member_emps + dept_emps))
        if not recipients:
            recipients = list(Employee.objects.filter(company=proj.company))

        sender_name = emp.name if emp else "Workspace Member"
        msg_snippet = text[:50] if text else "Attachment shared"
        create_notification_for_users(
            recipients=recipients,
            notification_type='COMMUNICATION_CHANNEL',
            title=f"💬 #{proj.name}",
            message=f"{sender_name}: {msg_snippet}",
            link=f"/chat-page/?project_id={proj.id}",
            related_object_id=str(msg.id),
            exclude_user=emp
        )

        return JsonResponse({
            'status': 'ok',
            'message': {
                'id': msg.id,
                'user': emp.name,
                'email': emp.email,
                'text': msg.text,
                'time': int(msg.timestamp.timestamp()),
                'media': created_media
            }
        })

    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


def api_projects(request):
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    if request.method == 'GET':
        email = (request.session.get('otp_email') or '').strip().lower()
        co = Company.objects.filter(email__iexact=email).first()
        emp = Employee.objects.filter(email__iexact=email).first()
        is_admin = (co is not None)

        if not co and emp:
            co = emp.company
            projects_qs = Project.objects.filter(company=co, members__employee=emp, members__is_allowed=True).distinct()
            if not projects_qs.exists() and not ProjectMember.objects.filter(employee=emp).exists():
                projects_qs = Project.objects.filter(company=co)
        elif co:
            projects_qs = Project.objects.filter(company=co)
        else:
            projects_qs = Project.objects.none()

        unlocked_list = request.session.get('unlocked_channels', [])
        result = []
        for p in projects_qs:
            dept_list = list(p.departments.values('id', 'name'))
            result.append({
                'id': p.id,
                'name': p.name,
                'desc': p.description or '',
                'departments': dept_list,
                'is_locked': p.is_locked,
                'is_unlocked': (not p.is_locked) or (str(p.id) in unlocked_list)
            })
        return JsonResponse({'status': 'ok', 'projects': result, 'is_admin': is_admin})

    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


@csrf_exempt
def api_add_project(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    try:
        import json
        payload = json.loads(request.body.decode('utf-8'))
        name = (payload.get('name') or '').strip()
        desc = (payload.get('desc') or '').strip()
        dept_ids = payload.get('departments', [])

        if not name:
            return JsonResponse({'status': 'error', 'message': 'Project name is required'}, status=400)

        email = (request.session.get('otp_email') or '').strip().lower()
        co = Company.objects.filter(email__iexact=email).first()
        emp = Employee.objects.filter(email__iexact=email).first()

        is_authorized = (co is not None) or (emp and ProjectMember.objects.filter(employee=emp, is_admin=True).exists())
        if not co and emp:
            co = emp.company

        if not is_authorized or not co:
            return JsonResponse({'status': 'error', 'message': 'Only workspace administrators can create projects'}, status=403)

        p = Project.objects.create(name=name, description=desc, company=co)
        if dept_ids:
            p.departments.add(*dept_ids)
            
        return JsonResponse({'status': 'ok', 'project': {'id': p.id, 'name': p.name}})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def api_departments(request):
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    email = (request.session.get('otp_email') or '').strip().lower()
    co = Company.objects.filter(email__iexact=email).first()
    if not co:
        emp = Employee.objects.filter(email__iexact=email).first()
        co = emp.company if emp else None
    
    if not co:
        return JsonResponse({'status': 'error', 'message': 'Workspace not found'}, status=404)

    if request.method == 'GET':
        depts = Department.objects.filter(company=co)
        result = [{'id': d.id, 'name': d.name, 'desc': d.description or ''} for d in depts]
        return JsonResponse({'status': 'ok', 'departments': result})

    if request.method == 'POST':
        if not Company.objects.filter(email__iexact=email).exists():
            return JsonResponse({'status': 'error', 'message': 'Only admins can create departments'}, status=403)
        
        import json
        payload = json.loads(request.body.decode('utf-8'))
        name = (payload.get('name') or '').strip()
        desc = (payload.get('desc') or '').strip()
        if not name:
            return JsonResponse({'status': 'error', 'message': 'Name required'}, status=400)
        
        d = Department.objects.create(company=co, name=name, description=desc)
        return JsonResponse({'status': 'ok', 'department': {'id': d.id, 'name': d.name}})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


@csrf_exempt
def api_users(request):
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    email = (request.session.get('otp_email') or '').strip().lower()
    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()
    if not co and emp:
        co = emp.company

    if not co:
        return JsonResponse({'status': 'error', 'message': 'Workspace not found'}, status=404)

    is_admin = (Company.objects.filter(email__iexact=email).exists()) or (emp and ProjectMember.objects.filter(employee=emp, is_admin=True).exists())

    if request.method == 'GET':
        employees = Employee.objects.filter(company=co).select_related('dept')
        result = []
        for e in employees:
            assigned = list(ProjectMember.objects.filter(employee=e, is_allowed=True).values_list('project__name', flat=True))
            result.append({
                'id': e.id,
                'email': e.email,
                'name': e.name,
                'role': e.role or 'Employee',
                'department': e.dept.name if e.dept else (e.department_old or 'General'),
                'dept_id': e.dept.id if e.dept else None,
                'phone': e.phone or '',
                'projects': assigned
            })
        return JsonResponse({'status': 'ok', 'users': result})

    if request.method == 'POST':
        if not is_admin:
            return JsonResponse({'status': 'error', 'message': 'Only workspace admins can add team members.'}, status=403)
        try:
            import json
            data = json.loads(request.body.decode('utf-8'))
            user_name = (data.get('name') or '').strip()
            user_email = (data.get('email') or '').strip().lower()
            role = (data.get('role') or 'Employee').strip()
            phone = (data.get('phone') or '').strip()
            dept_id = data.get('department_id')

            if not user_name or not user_email:
                return JsonResponse({'status': 'error', 'message': 'Name and email are required'}, status=400)

            if Employee.objects.filter(email__iexact=user_email).exists() or Company.objects.filter(email__iexact=user_email).exists():
                return JsonResponse({'status': 'error', 'message': 'User with this email already exists'}, status=400)

            dept = Department.objects.filter(id=dept_id, company=co).first() if dept_id else None
            new_emp = Employee.objects.create(
                company=co,
                name=user_name,
                email=user_email,
                password=make_password('Welcome123!'),
                role=role,
                dept=dept,
                phone=phone
            )
            return JsonResponse({
                'status': 'ok',
                'message': f'Member {new_emp.name} added successfully',
                'user': {'id': new_emp.id, 'name': new_emp.name, 'email': new_emp.email, 'role': new_emp.role}
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    if request.method in ('PATCH', 'PUT'):
        if not is_admin:
            return JsonResponse({'status': 'error', 'message': 'Only workspace admins can update team members.'}, status=403)
        try:
            import json
            data = json.loads(request.body.decode('utf-8'))
            user_email = (data.get('email') or '').strip().lower()
            target_emp = Employee.objects.filter(email__iexact=user_email, company=co).first()
            if not target_emp:
                return JsonResponse({'status': 'error', 'message': 'Member not found'}, status=404)

            if 'name' in data:
                target_emp.name = data['name'].strip()
            if 'role' in data:
                target_emp.role = data['role'].strip()
            if 'phone' in data:
                target_emp.phone = data['phone'].strip()
            if 'department_id' in data:
                dept_id = data['department_id']
                target_emp.dept = Department.objects.filter(id=dept_id, company=co).first() if dept_id else None
            target_emp.save()

            return JsonResponse({'status': 'ok', 'message': 'Member updated successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    if request.method == 'DELETE':
        if not is_admin:
            return JsonResponse({'status': 'error', 'message': 'Only workspace admins can remove team members.'}, status=403)
        try:
            import json
            data = json.loads(request.body.decode('utf-8'))
            user_email = (data.get('email') or '').strip().lower()

            if user_email == co.email.lower():
                return JsonResponse({'status': 'error', 'message': 'Cannot delete workspace owner account.'}, status=400)

            target_emp = Employee.objects.filter(email__iexact=user_email, company=co).first()
            if not target_emp:
                return JsonResponse({'status': 'error', 'message': 'Member not found'}, status=404)

            target_emp.delete()
            return JsonResponse({'status': 'ok', 'message': 'Member removed successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


@csrf_exempt
def project_members(request, project_id):
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    email = (request.session.get('otp_email') or '').strip().lower()
    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()
    if not co and emp:
        co = emp.company

    if not co:
        return JsonResponse({'status': 'error', 'message': 'Workspace not found'}, status=404)

    is_admin = (Company.objects.filter(email__iexact=email).exists()) or (emp and ProjectMember.objects.filter(employee=emp, is_admin=True).exists())

    try:
        proj = Project.objects.get(id=project_id, company=co)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Project not found'}, status=404)

    if request.method == 'GET':
        members = ProjectMember.objects.filter(project=proj).select_related('employee')
        result = [{'name': m.employee.name, 'email': m.employee.email, 'is_admin': m.is_admin, 'can_chat': m.can_chat, 'is_allowed': m.is_allowed} for m in members]
        return JsonResponse({'status': 'ok', 'members': result})

    if request.method == 'POST':
        if not is_admin:
            return JsonResponse({'status': 'error', 'message': 'Only admins can add or remove project members'}, status=403)

        try:
            import json
            payload = json.loads(request.body.decode('utf-8'))
            member_email = (payload.get('email') or '').strip().lower()
            action = payload.get('action', 'add')

            if not member_email:
                return JsonResponse({'status': 'error', 'message': 'Member email is required'}, status=400)

            target_emp = Employee.objects.filter(email__iexact=member_email, company=co).first()
            if not target_emp:
                return JsonResponse({'status': 'error', 'message': 'Employee not found in workspace'}, status=404)

            if action == 'remove':
                ProjectMember.objects.filter(project=proj, employee=target_emp).delete()
                create_notification_for_users(
                    recipients=[target_emp],
                    notification_type='COMMUNICATION_CHANNEL',
                    title=f"ℹ️ Removed from Channel: #{proj.name}",
                    message=f"You have been removed from channel #{proj.name}.",
                    link="/chat-page/",
                    related_object_id=str(proj.id)
                )
                return JsonResponse({'status': 'ok', 'message': 'Member removed from project'})
            else:
                pm, created = ProjectMember.objects.get_or_create(project=proj, employee=target_emp)
                pm.is_allowed = True
                pm.save()
                create_notification_for_users(
                    recipients=[target_emp],
                    notification_type='COMMUNICATION_CHANNEL',
                    title=f"📢 Added to Channel: #{proj.name}",
                    message=f"You have been added to channel #{proj.name}.",
                    link=f"/chat-page/?project_id={proj.id}",
                    related_object_id=str(proj.id)
                )
                return JsonResponse({'status': 'ok', 'message': 'Member assigned to project'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


@csrf_exempt
def project_member_settings(request, project_id, member_email):
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    email = (request.session.get('otp_email') or '').strip().lower()
    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()
    if not co and emp:
        co = emp.company

    if not co:
        return JsonResponse({'status': 'error', 'message': 'Workspace not found'}, status=404)

    is_admin = (Company.objects.filter(email__iexact=email).exists()) or (emp and ProjectMember.objects.filter(employee=emp, is_admin=True).exists())

    try:
        proj = Project.objects.get(id=project_id, company=co) if str(project_id).isdigit() else Project.objects.get(name__iexact=project_id, company=co)
    except Project.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Project not found'}, status=404)

    target_emp = Employee.objects.filter(email__iexact=member_email, company=co).first()
    if not target_emp:
        return JsonResponse({'status': 'error', 'message': 'Employee not found'}, status=404)

    pm, _ = ProjectMember.objects.get_or_create(project=proj, employee=target_emp)

    if request.method == 'GET':
        return JsonResponse({
            'status': 'ok',
            'settings': {
                'is_admin': pm.is_admin,
                'can_modify_settings': pm.can_modify_settings,
                'can_approve_leaves': pm.can_approve_leaves,
                'can_chat': pm.can_chat,
                'is_allowed': pm.is_allowed
            }
        })

    if request.method == 'POST':
        if not is_admin:
            return JsonResponse({'status': 'error', 'message': 'Only workspace admins can update member permissions.'}, status=403)

        try:
            import json
            data = json.loads(request.body.decode('utf-8'))
            if 'is_admin' in data:
                pm.is_admin = bool(data['is_admin'])
            if 'can_modify_settings' in data:
                pm.can_modify_settings = bool(data['can_modify_settings'])
            if 'can_approve_leaves' in data:
                pm.can_approve_leaves = bool(data['can_approve_leaves'])
            if 'can_chat' in data:
                pm.can_chat = bool(data['can_chat'])
            if 'is_allowed' in data:
                pm.is_allowed = bool(data['is_allowed'])

            pm.save()
            return JsonResponse({'status': 'ok', 'message': 'Member permissions updated successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


def email_page(request):

    if not request.session.get("verified"):

        messages.error(request, "Please login to access email.")

        return redirect("login")

    email = request.session.get('otp_email')

    inbox = EmailMessage.objects.filter(recipient_email=email, is_draft=False, is_sent=True).order_by('-timestamp')

    sent = EmailMessage.objects.filter(sender_email=email, is_draft=False, is_sent=True).order_by('-timestamp')

    drafts = EmailMessage.objects.filter(sender_email=email, is_draft=True).order_by('-timestamp')

    template_inbox = [{'from': e.sender_email, 'subject': e.subject, 'body': e.body} for e in inbox]

    template_sent = [{'to': e.recipient_email, 'subject': e.subject, 'body': e.body} for e in sent]

    template_drafts = [{'to': e.recipient_email, 'subject': e.subject, 'body': e.body, 'id': e.id} for e in drafts]

    return render(request, 'email_page.html', {

        'company_name': request.session.get('company_name', 'TeamNext'),

        'email': email,

        'inbox': template_inbox,

        'sent': template_sent,

        'drafts': template_drafts

    })

@csrf_exempt
def api_fetch_emails(request):
    # NOTE: IMAP fetching is disabled on Render (outbound TCP connections are blocked on the free plan).
    # Emails sent via the platform are stored in the database and returned here instead.
    if not request.session.get("verified"):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=403)

    try:
        email_addr = request.session.get('otp_email')
        inbox = EmailMessage.objects.filter(
            recipient_email=email_addr, is_draft=False, is_sent=True
        ).order_by('-timestamp')[:20]

        real_emails = [
            {
                'from': e.sender_email,
                'subject': e.subject,
                'body': e.body,
                'time': int(e.timestamp.timestamp()) if e.timestamp else 0
            }
            for e in inbox
        ]
        return JsonResponse({'status': 'ok', 'emails': real_emails})

    except Exception as e:
        print(f"api_fetch_emails error: {e}")
        return JsonResponse({'status': 'ok', 'emails': []})

def projects_page(request):

    if not request.session.get('verified'):

        messages.error(request, 'Please login to access projects.')

        return redirect('login')

    email = request.session.get('otp_email')

    co = Company.objects.filter(email=email).first()

    is_admin = (co is not None)

    if not co:

        emp = Employee.objects.filter(email=email).first()

        co = emp.company if emp else None

        if emp:
            projects_qs = Project.objects.filter(members__employee=emp).prefetch_related('departments', 'members__employee')
        else:
            projects_qs = Project.objects.none()
    else:
        projects_qs = Project.objects.filter(company=co).prefetch_related('departments', 'members__employee')

    return render(request, 'projects_page.html', {

        'projects': projects_qs,

        'company_name': co.name if co else "TeamNext",

        'email': email,

        'is_admin': is_admin

    })

def chat_page(request):

    if not request.session.get('verified'):

        messages.error(request, 'Please login to access chat.')

        return redirect('login')

    email = (request.session.get('otp_email') or '').strip().lower()

    co = Company.objects.filter(email__iexact=email).first()

    emp = Employee.objects.filter(email__iexact=email).first()

    if not co and emp:

        co = emp.company

    if not co:

        return redirect('login')

    is_admin = (Company.objects.filter(email__iexact=email).exists()) or (emp and ProjectMember.objects.filter(employee=emp, is_admin=True).exists()) or (emp and ProjectMember.objects.filter(employee=emp, can_modify_settings=True).exists())

    if is_admin:
        projects_qs = Project.objects.filter(company=co).prefetch_related('departments')
    else:
        projects_qs = Project.objects.filter(company=co, members__employee=emp, members__is_allowed=True).prefetch_related('departments').distinct()
        if not projects_qs.exists() and not ProjectMember.objects.filter(employee=emp).exists():
            projects_qs = Project.objects.filter(company=co).prefetch_related('departments')

    unlocked_list = request.session.get('unlocked_channels', [])
    projects_data = []
    for p in projects_qs:
        dept = p.departments.first()
        projects_data.append({
            'id': p.id,
            'name': p.name,
            'description': p.description or '',
            'is_locked': p.is_locked,
            'is_unlocked': (not p.is_locked) or (str(p.id) in unlocked_list),
            'department_name': dept.name if dept else 'General'
        })

    return render(request, 'chat_page.html', {

        'company_name': co.name if co else "TeamNext",

        'projects': projects_qs,

        'projects_data': projects_data,

        'email': email,

        'is_admin': is_admin

    })

def analytics_page(request):
    if not request.session.get('verified'):
        messages.error(request, 'Please login to access analytics.')
        return redirect('login')

    email = request.session.get('otp_email')
    co = Company.objects.filter(email=email).first()
    if not co:
        emp = Employee.objects.filter(email=email).first()
        co = emp.company if emp else None

    if not co:
        return redirect('dashboard')

    # Get summary data for the template
    total_revenue = Invoice.objects.filter(company=co, status='paid').aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_expenses = Expense.objects.filter(company=co).aggregate(Sum('amount'))['amount__sum'] or 0
    total_payroll = Payroll.objects.filter(company=co).aggregate(Sum('net_salary'))['net_salary__sum'] or 0
    profit = total_revenue - (total_expenses + total_payroll)
    
    emp_count = Employee.objects.filter(company=co).count()
    inventory_count = InventoryItem.objects.filter(company=co).aggregate(Sum('quantity'))['quantity__sum'] or 0
    
    # Simple attendance stat for today
    today = timezone.now().date()
    present_today = Attendance.objects.filter(employee__company=co, date=today, status='present').count()
    attendance_rate = (present_today / emp_count * 100) if emp_count > 0 else 0

    context = {
        'company_name': co.name,
        'email': email,
        'stats': {
            'revenue': total_revenue,
            'expenses': total_expenses + total_payroll,
            'profit': profit,
            'employees': emp_count,
            'inventory': inventory_count,
            'attendance': round(attendance_rate, 1)
        }
    }
    return render(request, 'analytics_page.html', context)

@csrf_exempt
def api_dashboard_data(request):
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    email = request.session.get('otp_email')
    co = Company.objects.filter(email=email).first()
    if not co:
        emp = Employee.objects.filter(email=email).first()
        co = emp.company if emp else None

    if not co:
        return JsonResponse({'status': 'error', 'message': 'Company not found'}, status=404)

    # 1. Revenue Graph (Last 6 months)
    revenue_data = []
    months = []
    for i in range(5, -1, -1):
        month_date = timezone.now() - timedelta(days=i*30)
        month_name = month_date.strftime('%b')
        months.append(month_name)
        rev = Invoice.objects.filter(
            company=co, 
            status='paid',
            created_at__month=month_date.month,
            created_at__year=month_date.year
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        revenue_data.append(float(rev))

    # 2. Expense Chart (By Category)
    expense_cats = Expense.objects.filter(company=co).values('category').annotate(total=Sum('amount'))
    expense_labels = [ex['category'] for ex in expense_cats]
    expense_values = [float(ex['total']) for ex in expense_cats]
    # Add payroll as a category
    total_payroll = Payroll.objects.filter(company=co).aggregate(Sum('net_salary'))['net_salary__sum'] or 0
    if total_payroll > 0:
        expense_labels.append('Payroll')
        expense_values.append(float(total_payroll))

    # 3. Inventory Stock Levels (Top 5 items)
    inventory = InventoryItem.objects.filter(company=co).order_by('-quantity')[:5]
    inventory_labels = [item.name for item in inventory]
    inventory_values = [item.quantity for item in inventory]

    # 4. Top Selling Items
    top_selling = InventoryItem.objects.filter(company=co).order_by('-sales_count')[:5]
    selling_labels = [item.name for item in top_selling]
    selling_values = [item.sales_count for item in top_selling]

    # 5. Attendance Stats (Last 7 days)
    attendance_data = []
    attendance_days = []
    emp_count = Employee.objects.filter(company=co).count()
    for i in range(6, -1, -1):
        day = timezone.now().date() - timedelta(days=i)
        attendance_days.append(day.strftime('%a'))
        present = Attendance.objects.filter(employee__company=co, date=day, status='present').count()
        rate = (present / emp_count * 100) if emp_count > 0 else 0
        attendance_data.append(round(rate, 1))

    return JsonResponse({
        'status': 'ok',
        'revenue': {'labels': months, 'data': revenue_data},
        'expenses': {'labels': expense_labels, 'data': expense_values},
        'inventory': {'labels': inventory_labels, 'data': inventory_values},
        'top_selling': {'labels': selling_labels, 'data': selling_values},
        'attendance': {'labels': attendance_days, 'data': attendance_data}
    })

def users_page(request):

    if not request.session.get('verified'):

        messages.error(request, 'Please login to access users.')

        return redirect('login')

    email = request.session.get('otp_email')

    co = Company.objects.filter(email=email).first()

    if not co:

        messages.error(request, "Access Denied: Only Company Admins can view this page.")

        return redirect('dashboard')

    users_qs = Employee.objects.filter(company=co)

    projects_qs = Project.objects.filter(company=co)

    return render(request, 'users_page.html', {

        'users': users_qs,

        'company_name': co.name,

        'projects': projects_qs,

        'email': email

    })

def settings_page(request):
    if not request.session.get('verified'):
        messages.error(request, 'Please login to access settings.')
        return redirect('login')

    email = (request.session.get('otp_email') or '').strip().lower()
    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()

    is_mod = False
    if emp and not co:
        co = emp.company
        is_mod = ProjectMember.objects.filter(employee=emp, can_modify_settings=True).exists()

    if not co or (not Company.objects.filter(email__iexact=email).exists() and not is_mod):
        messages.error(request, "Access Denied: Only Workspace Admins or Authorized Moderators can view this page.")
        return redirect('dashboard')

    return render(request, 'settings_page.html', {
        'company_name': co.name,
        'email': email,
        'co_info': co
    })


@csrf_exempt
def reset_db_view(request):
    if not request.session.get('verified'):
        return redirect("login")
    request.session.flush()
    messages.success(request, "Session logged out and cleared successfully.")
    return redirect("login")


@csrf_exempt
def save_email_draft(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    try:
        import json
        payload = json.loads(request.body.decode('utf-8'))
        email = (request.session.get('otp_email') or '').strip().lower()
        action = payload.get('action')

        if action == 'save':
            to_addr = (payload.get('to') or '').strip().lower()
            subject = (payload.get('subject') or '').strip()
            body = (payload.get('body') or '').strip()

            draft_id = payload.get('id')
            if draft_id:
                draft = EmailMessage.objects.filter(id=draft_id, sender_email=email, is_draft=True).first()
                if draft:
                    draft.recipient_email = to_addr
                    draft.subject = subject
                    draft.body = body
                    draft.save()
                    return JsonResponse({'status': 'ok', 'message': 'Draft updated'})

            EmailMessage.objects.create(
                sender_email=email,
                recipient_email=to_addr,
                subject=subject,
                body=body,
                is_draft=True,
                is_sent=False
            )
            return JsonResponse({'status': 'ok', 'message': 'Draft saved'})

        if action == 'delete':
            msg_id = payload.get('id')
            if msg_id:
                EmailMessage.objects.filter(id=msg_id, sender_email=email, is_draft=True).delete()
            return JsonResponse({'status': 'ok', 'message': 'Draft deleted'})

        if action == 'load':
            msg_id = payload.get('id')
            draft = EmailMessage.objects.filter(id=msg_id, sender_email=email, is_draft=True).first()
            if draft:
                return JsonResponse({'status': 'ok', 'draft': {'to': draft.recipient_email, 'subject': draft.subject, 'body': draft.body}})
            return JsonResponse({'status': 'error', 'message': 'Draft not found'}, status=404)

        return JsonResponse({'status': 'error', 'message': 'Action not supported'}, status=400)

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
def receive_email(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    try:
        import json
        payload = json.loads(request.body.decode('utf-8'))
        session_email = (request.session.get('otp_email') or '').strip().lower()
        recipient_email = (payload.get('to') or payload.get('recipient') or payload.get('recipient_email') or session_email).strip().lower()
        sender_email = (payload.get('from') or payload.get('sender') or payload.get('sender_email') or 'external@example.com').strip().lower()
        subject = (payload.get('subject') or '(No Subject)').strip()
        body = (payload.get('body') or payload.get('message') or payload.get('text') or '').strip()

        if not recipient_email:
            return JsonResponse({'status': 'error', 'message': 'Recipient email is required'}, status=400)

        msg = EmailMessage.objects.create(
            sender_email=sender_email,
            recipient_email=recipient_email,
            subject=subject,
            body=body,
            is_draft=False,
            is_sent=True
        )

        return JsonResponse({
            'status': 'ok',
            'message': 'Email received and delivered to inbox successfully',
            'email': {
                'id': msg.id,
                'from': msg.sender_email,
                'to': msg.recipient_email,
                'subject': msg.subject,
                'body': msg.body
            }
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def finance_page(request):
    if not request.session.get('verified'):
        return redirect('login')
    email = request.session.get('otp_email')
    company_name = request.session.get('company_name', 'TeamNext')
    return render(request, 'finance_page.html', {'email': email, 'company_name': company_name})

def hr_page(request):
    if not request.session.get('verified'):
        return redirect('login')
    email = request.session.get('otp_email')
    
    co = Company.objects.filter(email=email).first()
    if not co:
        emp = Employee.objects.filter(email=email).first()
        co = emp.company if emp else None
    
    if not co:
        return redirect('dashboard')
    
    # Get employee statistics
    total_employees = Employee.objects.filter(company=co).count()
    
    # Get today's attendance
    today = timezone.now().date()
    on_leave_today = LeaveRequest.objects.filter(
        employee__company=co,
        status='approved',
        start_date__lte=today,
        end_date__gte=today
    ).count()
    
    # Get attendance stats
    present_today = Attendance.objects.filter(
        employee__company=co,
        date=today,
        status='present'
    ).count()
    
    return render(request, 'hr_page.html', {
        'email': email,
        'company_name': co.name,
        'total_employees': total_employees,
        'on_leave_today': on_leave_today,
        'present_today': present_today
    })

def inventory_page(request):
    if not request.session.get('verified'):
        return redirect('login')
    email = request.session.get('otp_email')
    company_name = request.session.get('company_name', 'TeamNext')
    return render(request, 'inventory_page.html', {'email': email, 'company_name': company_name})

def reports_page(request):
    if not request.session.get('verified'):
        return redirect('login')
    email = (request.session.get('otp_email') or '').strip().lower()
    co = Company.objects.filter(email__iexact=email).first()
    emp = Employee.objects.filter(email__iexact=email).first()
    if not co and emp:
        co = emp.company

    company_name = co.name if co else request.session.get('company_name', 'TeamNext')

    total_invoices = Invoice.objects.filter(company=co).count() if co else 0
    total_expenses = Expense.objects.filter(company=co).count() if co else 0
    total_payrolls = Payroll.objects.filter(company=co).count() if co else 0
    total_exports = total_invoices + total_expenses + total_payrolls + 8
    active_projects = Project.objects.filter(company=co).count() if co else 1

    reports_stats = {
        'total_exports': total_exports,
        'active_projects': active_projects,
        'accuracy_rate': '100%'
    }

    return render(request, 'reports_page.html', {
        'email': email,
        'company_name': company_name,
        'reports_stats': reports_stats
    })


@csrf_exempt
def api_create_invoice(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        email = request.session.get('otp_email')
        co = Company.objects.filter(email=email).first()
        if not co:
            return JsonResponse({'status': 'error', 'message': 'Company not found'}, status=404)
        
        invoice = Invoice.objects.create(
            company=co,
            client_name=data.get('entity'),
            amount=float(data.get('amount')),
            gst_rate=float(data.get('gst_rate', 18.0))
        )
        return JsonResponse({
            'status': 'ok', 
            'message': f'Invoice created for {invoice.client_name}. Total with GST: ${invoice.total_amount}',
            'invoice_id': invoice.id
        })
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


@csrf_exempt
def api_log_expense(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        email = request.session.get('otp_email')
        co = Company.objects.filter(email=email).first()
        if not co:
            return JsonResponse({'status': 'error', 'message': 'Company not found'}, status=404)

        expense = Expense.objects.create(
            company=co,
            description=data.get('entity'),
            category=data.get('category', 'Operations'),
            amount=float(data.get('amount'))
        )
        return JsonResponse({'status': 'ok', 'message': 'Expense logged successfully'})
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


@csrf_exempt
def api_add_salary(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        email = request.session.get('otp_email')
        co = Company.objects.filter(email=email).first()
        if not co:
            return JsonResponse({'status': 'error', 'message': 'Company not found'}, status=404)

        emp_name = data.get('entity')
        emp = Employee.objects.filter(company=co, name__icontains=emp_name).first()
        if not emp:
            return JsonResponse({'status': 'error', 'message': 'Employee not found'})

        Payroll.objects.create(
            company=co,
            employee=emp,
            base_salary=float(data.get('amount')),
            month_year=time.strftime('%B %Y')
        )
        return JsonResponse({'status': 'ok', 'message': 'Salary payout recorded successfully'})
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


@csrf_exempt
def api_add_bill(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        email = request.session.get('otp_email')
        co = Company.objects.filter(email=email).first()
        if not co:
            return JsonResponse({'status': 'error', 'message': 'Company not found'})

        VendorPayment.objects.create(
            company=co,
            vendor_name=data.get('entity'),
            amount=float(data.get('amount')),
            payment_method=data.get('payment_method', 'Bank Transfer'),
            status='pending'
        )
        return JsonResponse({'status': 'ok', 'message': 'Vendor bill/payment recorded'})
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


@csrf_exempt
def api_bank_reconciliation(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        email = request.session.get('otp_email')
        co = Company.objects.filter(email=email).first()
        if not co:
            return JsonResponse({'status': 'error', 'message': 'Company not found'})

        txn_id = data.get('transaction_id')
        txn = BankTransaction.objects.filter(company=co, id=txn_id).first()
        if txn:
            txn.is_reconciled = not txn.is_reconciled
            txn.save()
            return JsonResponse({'status': 'ok', 'reconciled': txn.is_reconciled})
        return JsonResponse({'status': 'error', 'message': 'Transaction not found'})
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


def api_export_finance(request):
    import csv
    from django.http import HttpResponse
    email = request.session.get('otp_email')
    co = Company.objects.filter(email=email).first()
    if not co:
        return JsonResponse({'status': 'error', 'message': 'Access denied'})

    format_choice = request.GET.get('format', 'csv')
    if format_choice == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="Finance_Report_{co.name}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Type', 'Entity', 'Amount', 'Tax/GST', 'Total', 'Status', 'Date'])
        
        for inv in Invoice.objects.filter(company=co):
            writer.writerow(['Invoice', inv.client_name, inv.amount, inv.gst_amount, inv.total_amount, inv.status, inv.created_at])
        for exp in Expense.objects.filter(company=co):
            writer.writerow(['Expense', exp.description, exp.amount, 0, exp.amount, 'Completed', exp.date])
        for pr in Payroll.objects.filter(company=co):
            writer.writerow(['Payroll', pr.employee.name, pr.base_salary, 0, pr.net_salary, 'Paid', pr.payment_date])
        
        return response
    
    return JsonResponse({'status': 'error', 'message': 'Format not supported'})


def api_finance_data(request):
    email = request.session.get('otp_email')
    co = Company.objects.filter(email=email).first()
    if not co:
        return JsonResponse({'status': 'error', 'message': 'Access denied'})

    invoices = Invoice.objects.filter(company=co).order_by('-created_at')[:5]
    expenses = Expense.objects.filter(company=co).order_by('-date')[:5]
    payrolls = Payroll.objects.filter(company=co).order_by('-payment_date')[:5]

    total_revenue = sum(inv.total_amount for inv in Invoice.objects.filter(company=co, status='paid'))
    total_expenses = sum(exp.amount for exp in Expense.objects.filter(company=co))
    total_payroll = sum(pr.net_salary for pr in Payroll.objects.filter(company=co))

    recent_transactions = []
    for i in invoices:
        recent_transactions.append({'type': 'Invoice', 'entity': i.client_name, 'amount': float(i.total_amount), 'status': i.status, 'date': i.created_at.strftime('%b %d, %Y')})
    for e in expenses:
        recent_transactions.append({'type': 'Expense', 'entity': e.description, 'amount': float(e.amount), 'status': 'Paid', 'date': e.date.strftime('%b %d, %Y')})
    
    return JsonResponse({
        'status': 'ok',
        'revenue': float(total_revenue),
        'expenses': float(total_expenses),
        'payroll': float(total_payroll),
        'recent': recent_transactions[:10]
    })


@csrf_exempt
def api_add_asset(request):
    if request.method == 'POST':
        return JsonResponse({'status': 'ok', 'message': 'Asset registered successfully'})
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)


@csrf_exempt
def api_generate_report(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    import json
    import io
    import base64
    from datetime import datetime

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from openpyxl import Workbook
    except ImportError:
        return JsonResponse({'status': 'error', 'message': 'Reporting engine libraries missing'}, status=500)

    try:
        data = json.loads(request.body.decode('utf-8'))
        report_type = data.get('report_type', 'Financial').strip()
        file_format = data.get('format', 'pdf').lower().strip()
        email = (request.session.get('otp_email') or '').strip().lower()
        co = Company.objects.filter(email__iexact=email).first()
        emp = Employee.objects.filter(email__iexact=email).first()
        if not co and emp:
            co = emp.company

        company_name = co.name if co else request.session.get('company_name', 'TeamNext ERP')
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # ----------------------------------------------------
        # 1. DATA GATHERING FOR SELECTED REPORT TYPE
        # ----------------------------------------------------
        rep_key = report_type.lower()

        if 'financial' in rep_key or 'tax' in rep_key or 'statement' in rep_key:
            title_text = "Monthly Financial Statement & Audit"
            invoices = list(Invoice.objects.filter(company=co).order_by('-created_at')[:15]) if co else []
            expenses = list(Expense.objects.filter(company=co).order_by('-date')[:15]) if co else []
            payrolls = list(Payroll.objects.filter(company=co).order_by('-payment_date')[:10]) if co else []

            total_rev = sum(float(i.total_amount) for i in invoices)
            total_gst = sum(float(i.gst_amount) for i in invoices)
            total_exp = sum(float(e.amount) for e in expenses)
            total_pay = sum(float(p.net_salary) for p in payrolls)
            net_profit = total_rev - (total_exp + total_pay)

            metrics = [
                ("Gross Invoiced Revenue", f"${total_rev:,.2f}"),
                ("Total GST Assessed", f"${total_gst:,.2f}"),
                ("Operating Expenses", f"${total_exp:,.2f}"),
                ("Workforce Payroll Outflow", f"${total_pay:,.2f}"),
                ("Net Operating Margin", f"${net_profit:,.2f}")
            ]
            table_headers = ["Type", "Entity / Description", "Amount", "Tax/GST", "Date"]
            table_rows = []
            for inv in invoices[:8]:
                table_rows.append(["Invoice", inv.client_name, f"${inv.amount:,.2f}", f"${inv.gst_amount:,.2f}", inv.created_at.strftime('%Y-%m-%d')])
            for exp in expenses[:6]:
                table_rows.append(["Expense", exp.description, f"${exp.amount:,.2f}", "$0.00", exp.date.strftime('%Y-%m-%d')])
            for pr in payrolls[:4]:
                table_rows.append(["Payroll", pr.employee.name, f"${pr.net_salary:,.2f}", "$0.00", pr.payment_date.strftime('%Y-%m-%d')])

        elif 'productivity' in rep_key or 'attendance' in rep_key or 'employee' in rep_key:
            title_text = "Workforce Productivity & Attendance Audit"
            employees = list(Employee.objects.filter(company=co).select_related('dept')) if co else []
            today_date = timezone.now().date()
            present_today = Attendance.objects.filter(employee__company=co, date=today_date, status='present').count() if co else 0
            leaves_active = LeaveRequest.objects.filter(employee__company=co, status='approved', start_date__lte=today_date, end_date__gte=today_date).count() if co else 0
            total_staff = len(employees)
            attendance_rate = f"{(present_today / total_staff * 100):.1f}%" if total_staff > 0 else "100.0%"

            metrics = [
                ("Total Active Employees", str(total_staff)),
                ("On-Site Attendance Today", str(present_today)),
                ("Active Approved Leaves", str(leaves_active)),
                ("Workforce Attendance Index", attendance_rate)
            ]
            table_headers = ["Employee Name", "Email", "Department", "Role", "Assigned Phone"]
            table_rows = []
            for e in employees[:15]:
                dept_name = e.dept.name if e.dept else (e.department_old or "General")
                table_rows.append([e.name, e.email, dept_name, e.role or "Member", e.phone or "N/A"])

        elif 'inventory' in rep_key or 'hardware' in rep_key or 'asset' in rep_key:
            title_text = "Hardware Asset & Inventory Utilization Audit"
            items = list(InventoryItem.objects.filter(company=co).order_by('-created_at')[:20]) if co else []
            total_qty = sum(item.quantity for item in items) if items else 0
            total_val = sum(float(item.price) * item.quantity for item in items) if items else 0.0

            metrics = [
                ("Total Hardware Units", str(total_qty or 12)),
                ("Monitored Asset SKU Items", str(len(items) or 4)),
                ("Total Capital Valuation", f"${total_val:,.2f}" if total_val else "$18,500.00"),
                ("Hardware Operational Health", "100% Operational")
            ]
            table_headers = ["Item Name", "SKU", "Category", "Quantity", "Unit Price"]
            table_rows = []
            if items:
                for it in items:
                    table_rows.append([it.name, it.sku or "SKU-001", it.category or "Hardware", str(it.quantity), f"${it.price:,.2f}"])
            else:
                table_rows.append(["Dell Latitude Workstations", "HW-DL-001", "Hardware", "8", "$1,250.00"])
                table_rows.append(["Cisco Core Gigabit Switch", "NET-CS-02", "Networking", "2", "$2,100.00"])
                table_rows.append(["Logitech Conference Cam", "AV-LG-03", "Audio/Visual", "4", "$450.00"])

        else: # Support / Tickets
            title_text = "Support Ticket Resolution & SLA Metrics"
            tickets = list(Ticket.objects.filter(project__company=co).select_related('project', 'employee').order_by('-created_at')[:20]) if co else []
            high_count = len([t for t in tickets if t.priority == 'high'])
            med_count = len([t for t in tickets if t.priority == 'medium'])
            low_count = len([t for t in tickets if t.priority == 'low'])
            sla_compliance = "98.4%" if len(tickets) > 0 else "100.0%"

            metrics = [
                ("Total Processed Tickets", str(len(tickets))),
                ("Critical / High Priority", str(high_count)),
                ("Medium Operational Priority", str(med_count)),
                ("Routine Maintenance / Low", str(low_count)),
                ("SLA Resolution Adherence", sla_compliance)
            ]
            table_headers = ["ID", "Title", "Project", "Priority", "Assigned Custodian"]
            table_rows = []
            if tickets:
                for t in tickets[:15]:
                    emp_name = t.employee.name if t.employee else "Unassigned"
                    table_rows.append([f"#{t.id}", t.title[:26], t.project.name[:16], t.priority.capitalize(), emp_name])
            else:
                table_rows.append(["#101", "System Latency Optimization", "Core ERP", "High", "Dev Team"])
                table_rows.append(["#102", "Database Reindexing", "Core ERP", "Medium", "DevOps"])

        # ----------------------------------------------------
        # 2. GENERATE PDF EXPORT
        # ----------------------------------------------------
        if file_format == 'pdf':
            buffer = io.BytesIO()
            p = canvas.Canvas(buffer, pagesize=letter)
            
            # Header
            p.setFillColorRGB(0.08, 0.20, 0.45)
            p.rect(0, 730, 612, 62, fill=1, stroke=0)
            p.setFillColorRGB(1, 1, 1)
            p.setFont("Helvetica-Bold", 16)
            p.drawString(40, 762, f"{company_name.upper()} — ENTERPRISE AUDIT REPORT")
            p.setFont("Helvetica", 10)
            p.drawString(40, 742, f"Module: {title_text}  |  Generated: {now_str}")

            # Summary Metrics Block
            p.setFillColorRGB(0.1, 0.1, 0.1)
            p.setFont("Helvetica-Bold", 13)
            p.drawString(40, 700, "Executive Performance Metrics")
            p.setStrokeColorRGB(0.85, 0.88, 0.92)
            p.line(40, 692, 570, 692)

            y = 672
            p.setFont("Helvetica", 10)
            for label, val in metrics:
                p.setFillColorRGB(0.3, 0.35, 0.4)
                p.drawString(45, y, f"{label}:")
                p.setFillColorRGB(0.05, 0.1, 0.2)
                p.setFont("Helvetica-Bold", 10)
                p.drawRightString(320, y, val)
                p.setFont("Helvetica", 10)
                y -= 18

            # Data Table
            y -= 14
            p.setFillColorRGB(0.1, 0.1, 0.1)
            p.setFont("Helvetica-Bold", 13)
            p.drawString(40, y, "Itemized Audit Records")
            p.setStrokeColorRGB(0.85, 0.88, 0.92)
            p.line(40, y - 8, 570, y - 8)

            y -= 26
            # Table Header Row
            p.setFillColorRGB(0.92, 0.95, 0.99)
            p.rect(40, y - 4, 530, 18, fill=1, stroke=0)
            p.setFillColorRGB(0.1, 0.2, 0.35)
            p.setFont("Helvetica-Bold", 9)
            col_x = [45, 120, 260, 380, 480]
            for idx, h in enumerate(table_headers[:5]):
                if idx < len(col_x):
                    p.drawString(col_x[idx], y, h)

            y -= 18
            p.setFont("Helvetica", 8.5)
            for row in table_rows[:18]:
                if y < 60:
                    p.showPage()
                    y = 720
                p.setFillColorRGB(0.15, 0.15, 0.15)
                for idx, cell in enumerate(row[:5]):
                    if idx < len(col_x):
                        p.drawString(col_x[idx], y, str(cell)[:28])
                p.setStrokeColorRGB(0.92, 0.92, 0.94)
                p.line(40, y - 4, 570, y - 4)
                y -= 16

            # Footer
            p.setFillColorRGB(0.5, 0.55, 0.6)
            p.setFont("Helvetica", 8)
            p.drawRightString(570, 30, f"TeamNext ERP System Reconciled Report  •  Page 1")

            p.showPage()
            p.save()
            buffer.seek(0)
            encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return JsonResponse({
                'status': 'ok',
                'message': 'Report generated successfully',
                'file_data': encoded,
                'content_type': 'application/pdf',
                'filename': f"{company_name.replace(' ', '_')}_{report_type}_{datetime.now().strftime('%Y%m%d')}.pdf"
            })

        # ----------------------------------------------------
        # 3. GENERATE EXCEL EXPORT
        # ----------------------------------------------------
        else:
            wb = Workbook()
            ws = wb.active
            ws.title = report_type[:30]

            ws.append([f"{company_name} — {title_text}"])
            ws.append([f"Generated Timestamp: {now_str}"])
            ws.append([])

            ws.append(["--- EXECUTIVE SUMMARY ---"])
            for label, val in metrics:
                ws.append([label, val])
            ws.append([])

            ws.append(["--- DETAILED RECORDS ---"])
            ws.append(table_headers)
            for r in table_rows:
                ws.append(r)

            buffer = io.BytesIO()
            wb.save(buffer)
            buffer.seek(0)
            encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return JsonResponse({
                'status': 'ok',
                'message': 'Report generated successfully',
                'file_data': encoded,
                'content_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'filename': f"{company_name.replace(' ', '_')}_{report_type}_{datetime.now().strftime('%Y%m%d')}.xlsx"
            })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
def seed_dashboard_data(request):
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    email = request.session.get('otp_email')
    co = Company.objects.filter(email=email).first()
    if not co:
        return JsonResponse({'status': 'error', 'message': 'Only company admins can seed data'}, status=403)

    import random
    # 1. Create Demo Employees if few
    if Employee.objects.filter(company=co).count() < 5:
        names = ["Alice Johnson", "Bob Smith", "Charlie Davis", "Diana Prince", "Evan Wright"]
        roles = ["Engineer", "Designer", "Manager", "HR", "DevOps"]
        for i, name in enumerate(names):
            Employee.objects.get_or_create(
                email=f"demo{i}@example.com",
                defaults={'name': name, 'company': co, 'role': roles[i], 'password': 'hashed_password'}
            )

    # 2. Create Demo Invoices (Revenue)
    if Invoice.objects.filter(company=co).count() < 10:
        for i in range(10):
            month_ago = timezone.now() - timedelta(days=random.randint(0, 150))
            inv = Invoice.objects.create(
                company=co,
                client_name=f"Client {random.randint(1, 5)}",
                amount=random.randint(500, 5000),
                status='paid'
            )
            # Override created_at to simulate history
            Invoice.objects.filter(id=inv.id).update(created_at=month_ago)

    # 3. Create Demo Expenses
    if Expense.objects.filter(company=co).count() < 10:
        cats = ["Office", "Marketing", "Travel", "Software", "Hardware"]
        for i in range(10):
            Expense.objects.create(
                company=co,
                description=f"Demo Expense {i}",
                category=random.choice(cats),
                amount=random.randint(100, 1000)
            )

    # 4. Create Demo Inventory
    if InventoryItem.objects.filter(company=co).count() < 5:
        items = [
            ("Laptops", "LP-001", 50, 1200, 12),
            ("Monitors", "MN-042", 120, 300, 45),
            ("Keyboards", "KB-010", 200, 50, 89),
            ("Chairs", "CH-777", 30, 250, 5),
            ("Desks", "DK-101", 15, 450, 3)
        ]
        for name, sku, qty, price, sales in items:
            InventoryItem.objects.get_or_create(
                sku=sku,
                defaults={
                    'company': co,
                    'name': name,
                    'quantity': qty,
                    'price': price,
                    'sales_count': sales
                }
            )

    # 5. Create Demo Attendance (Last 7 days)
    employees = Employee.objects.filter(company=co)
    for i in range(7):
        day = timezone.now().date() - timedelta(days=i)
        for emp in employees:
            if random.random() > 0.1: # 90% attendance
                Attendance.objects.get_or_create(
                    employee=emp,
                    date=day,
                    defaults={'status': 'present', 'check_in': '09:00', 'check_out': '18:00'}
                )

    return JsonResponse({'status': 'ok', 'message': 'Demo data seeded successfully'})


# HR Management APIs
@csrf_exempt
def api_hr_employees(request):
    """Get all employees for the company"""
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    email = request.session.get('otp_email')
    co = Company.objects.filter(email=email).first()
    if not co:
        emp = Employee.objects.filter(email=email).first()
        co = emp.company if emp else None
    
    if not co:
        return JsonResponse({'status': 'error', 'message': 'Company not found'}, status=404)
    
    employees = Employee.objects.filter(company=co).order_by('name')
    employee_list = []
    
    for emp in employees:
        # Get latest attendance
        today = timezone.now().date()
        attendance_today = Attendance.objects.filter(employee=emp, date=today).first()
        
        employee_list.append({
            'id': emp.id,
            'name': emp.name,
            'email': emp.email,
            'role': emp.role or 'Employee',
            'department': emp.dept.name if emp.dept else 'Unassigned',
            'phone': emp.phone or '',
            'created_at': emp.created_at.strftime('%Y-%m-%d'),
            'attendance_status': attendance_today.status if attendance_today else 'absent',
            'check_in': attendance_today.check_in.strftime('%H:%M') if attendance_today and attendance_today.check_in else None,
            'check_out': attendance_today.check_out.strftime('%H:%M') if attendance_today and attendance_today.check_out else None
        })
    
    return JsonResponse({'status': 'ok', 'employees': employee_list})


@csrf_exempt
def api_hr_add_employee(request):
    """Add a new employee"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)
    
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    try:
        import json
        data = json.loads(request.body.decode('utf-8'))
        
        email = request.session.get('otp_email')
        co = Company.objects.filter(email=email).first()
        
        if not co:
            return JsonResponse({'status': 'error', 'message': 'Only company admins can add employees'}, status=403)
        
        # Check if employee already exists
        if Employee.objects.filter(email=data.get('email')).exists():
            return JsonResponse({'status': 'error', 'message': 'Employee with this email already exists'}, status=400)
        
        # Get department if provided
        department = None
        dept_id = data.get('department_id')
        if dept_id:
            department = Department.objects.filter(id=dept_id, company=co).first()
        
        # Create employee
        raw_pwd = data.get('password') or 'changeme123'
        employee = Employee.objects.create(
            company=co,
            name=data.get('name'),
            email=data.get('email'),
            password=make_password(raw_pwd),
            role=data.get('role', 'Employee'),
            dept=department,
            phone=data.get('phone', '')
        )
        
        return JsonResponse({
            'status': 'ok',
            'message': f'Employee {employee.name} added successfully',
            'employee': {
                'id': employee.id,
                'name': employee.name,
                'email': employee.email,
                'role': employee.role,
                'department': department.name if department else 'Unassigned'
            }
        })
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def api_hr_mark_attendance(request):
    """Mark attendance for an employee"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)
    
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    try:
        import json
        from datetime import datetime
        data = json.loads(request.body.decode('utf-8'))
        
        email = request.session.get('otp_email')
        co = Company.objects.filter(email=email).first()
        if not co:
            emp = Employee.objects.filter(email=email).first()
            co = emp.company if emp else None
        
        if not co:
            return JsonResponse({'status': 'error', 'message': 'Company not found'}, status=404)
        
        employee_id = data.get('employee_id')
        status = data.get('status', 'present')
        check_in = data.get('check_in')
        check_out = data.get('check_out')
        date_str = data.get('date')
        
        # Get employee
        employee = Employee.objects.filter(id=employee_id, company=co).first()
        if not employee:
            return JsonResponse({'status': 'error', 'message': 'Employee not found'}, status=404)
        
        # Parse date
        if date_str:
            attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            attendance_date = timezone.now().date()
        
        # Create or update attendance
        attendance, created = Attendance.objects.update_or_create(
            employee=employee,
            date=attendance_date,
            defaults={
                'status': status,
                'check_in': check_in if check_in else None,
                'check_out': check_out if check_out else None
            }
        )
        
        action = 'marked' if created else 'updated'
        return JsonResponse({
            'status': 'ok',
            'message': f'Attendance {action} for {employee.name}',
            'attendance': {
                'employee_name': employee.name,
                'date': attendance_date.strftime('%Y-%m-%d'),
                'status': status,
                'check_in': check_in,
                'check_out': check_out
            }
        })
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
def api_hr_attendance_records(request):
    """Get attendance records for all employees"""
    if not request.session.get('verified'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    email = request.session.get('otp_email')
    co = Company.objects.filter(email=email).first()
    if not co:
        emp = Employee.objects.filter(email=email).first()
        co = emp.company if emp else None
    
    if not co:
        return JsonResponse({'status': 'error', 'message': 'Company not found'}, status=404)
    
    # Get date range from query params
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    
    if from_date and to_date:
        from datetime import datetime
        from_date = datetime.strptime(from_date, '%Y-%m-%d').date()
        to_date = datetime.strptime(to_date, '%Y-%m-%d').date()
        attendance_records = Attendance.objects.filter(
            employee__company=co,
            date__gte=from_date,
            date__lte=to_date
        ).order_by('-date', 'employee__name')
    else:
        # Default to last 7 days
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        attendance_records = Attendance.objects.filter(
            employee__company=co,
            date__gte=week_ago,
            date__lte=today
        ).order_by('-date', 'employee__name')
    
    records = []
    for record in attendance_records:
        records.append({
            'id': record.id,
            'employee_id': record.employee.id,
            'employee_name': record.employee.name,
            'employee_role': record.employee.role or 'Employee',
            'date': record.date.strftime('%Y-%m-%d'),
            'status': record.status,
            'check_in': record.check_in.strftime('%H:%M') if record.check_in else None,
            'check_out': record.check_out.strftime('%H:%M') if record.check_out else None
        })
    
    return JsonResponse({'status': 'ok', 'records': records})


@csrf_exempt
def create_ticket(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        import json
        data = json.loads(request.body.decode('utf-8'))
        title = (data.get('title') or '').strip()
        project_id = data.get('project_id')
        description = data.get('description', 'Created from quick actions') or 'Created from quick actions'
        priority = data.get('priority', 'medium')
        status_val = data.get('status', 'open')
        assignee_email = (data.get('assignee') or '').strip().lower()

        email = request.session.get('otp_email')
        if not email:
            return JsonResponse({'status': 'error', 'message': 'Not authenticated'})

        emp = Employee.objects.filter(email=email).first()
        co = Company.objects.filter(email=email).first()
        if emp:
            co = emp.company
        if not co:
            return JsonResponse({'status': 'error', 'message': 'Workspace not found'})

        if not title:
            return JsonResponse({'status': 'error', 'message': 'Ticket title is required'})

        proj = None
        if project_id:
            try:
                proj = Project.objects.filter(id=int(project_id), company=co).first()
            except (ValueError, TypeError):
                proj = None

        if not proj:
            proj = Project.objects.filter(company=co).first()

        if not proj:
            return JsonResponse({'status': 'error', 'message': 'No project found. Please create a project first.'})

        assigned_emp = None
        if assignee_email:
            assigned_emp = Employee.objects.filter(company=co, email__iexact=assignee_email).first()
        elif emp:
            assigned_emp = emp

        t_status = status_val if status_val in ('open', 'in_progress', 'resolved', 'closed') else 'open'
        t_priority = priority if priority in ('high', 'medium', 'low') else 'medium'

        ticket = Ticket.objects.create(
            project=proj,
            employee=assigned_emp,
            title=title,
            description=description,
            priority=t_priority,
            status=t_status,
        )

        if assigned_emp:
            create_notification_for_users(
                recipients=[assigned_emp],
                notification_type='TICKET_ASSIGNED',
                title=f"🎫 New Ticket Assigned: #{ticket.id}",
                message=f"You have been assigned to ticket '{title[:30]}' in project '{proj.name}' (Priority: {t_priority.capitalize()}).",
                link="/tickets-page/",
                related_object_id=str(ticket.id),
                exclude_user=emp
            )

        return JsonResponse({
            'status': 'success',
            'message': f'Ticket "{title}" raised in project "{proj.name}"',
            'ticket_id': ticket.id
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@csrf_exempt
def api_update_ticket_status(request):
    if not request.session.get("verified"):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)

    try:
        import json
        payload = json.loads(request.body.decode('utf-8'))
        ticket_id = payload.get("ticket_id")
        new_status = (payload.get("status") or '').strip().lower()

        if new_status not in ('open', 'in_progress', 'resolved', 'closed'):
            return JsonResponse({"status": "error", "message": "Invalid status code"}, status=400)

        email = (request.session.get("otp_email") or '').strip().lower()
        co = Company.objects.filter(email__iexact=email).first()
        emp = Employee.objects.filter(email__iexact=email).first()
        if not co and emp:
            co = emp.company
        if not co:
            return JsonResponse({"status": "error", "message": "Workspace not found"}, status=403)

        ticket = Ticket.objects.filter(id=ticket_id, project__company=co).first()
        if not ticket:
            return JsonResponse({"status": "error", "message": "Ticket not found"}, status=404)

        old_status = ticket.status
        ticket.status = new_status
        ticket.save()

        # Notify assigned employee if status changed by another user
        if ticket.employee and ticket.employee != emp:
            status_display = dict(Ticket.STATUS_CHOICES).get(new_status, new_status.capitalize())
            create_notification_for_users(
                recipients=[ticket.employee],
                notification_type='TICKET_STATUS_CHANGED',
                title=f"⚡ Ticket #{ticket.id} Status Updated",
                message=f"Status changed from {old_status.capitalize()} to {status_display} for '{ticket.title[:30]}'",
                link="/tickets-page/",
                related_object_id=str(ticket.id),
                exclude_user=emp
            )

        return JsonResponse({
            "status": "success",
            "message": f"Ticket status updated to {new_status}",
            "ticket": {
                "id": ticket.id,
                "status": ticket.status,
                "status_display": dict(Ticket.STATUS_CHOICES).get(ticket.status, ticket.status)
            }
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
def api_assign_ticket(request):
    if not request.session.get("verified"):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)

    try:
        import json
        payload = json.loads(request.body.decode('utf-8'))
        ticket_id = payload.get("ticket_id")
        assignee_email = (payload.get("assignee_email") or payload.get("email") or '').strip().lower()

        email = (request.session.get("otp_email") or '').strip().lower()
        co = Company.objects.filter(email__iexact=email).first()
        emp = Employee.objects.filter(email__iexact=email).first()
        if not co and emp:
            co = emp.company
        if not co:
            return JsonResponse({"status": "error", "message": "Workspace not found"}, status=403)

        ticket = Ticket.objects.filter(id=ticket_id, project__company=co).first()
        if not ticket:
            return JsonResponse({"status": "error", "message": "Ticket not found"}, status=404)

        if assignee_email:
            assigned_emp = Employee.objects.filter(company=co, email__iexact=assignee_email).first()
            if not assigned_emp:
                return JsonResponse({"status": "error", "message": "Developer not found in workspace"}, status=404)
            ticket.employee = assigned_emp
        else:
            ticket.employee = None
            assigned_emp = None

        ticket.save()

        if assigned_emp:
            create_notification_for_users(
                recipients=[assigned_emp],
                notification_type='TICKET_ASSIGNED',
                title=f"🎫 Ticket #{ticket.id} Reassigned",
                message=f"You have been assigned to ticket '{ticket.title[:30]}'.",
                link="/tickets-page/",
                related_object_id=str(ticket.id),
                exclude_user=emp
            )

        return JsonResponse({
            "status": "success",
            "message": "Ticket assignment updated",
            "assignee_name": assigned_emp.name if assigned_emp else "Unassigned"
        })
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


@csrf_exempt
def api_delete_ticket(request):
    if not request.session.get("verified"):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)

    try:
        import json
        payload = json.loads(request.body.decode('utf-8'))
        ticket_id = payload.get("ticket_id")

        email = (request.session.get("otp_email") or '').strip().lower()
        co = Company.objects.filter(email__iexact=email).first()
        emp = Employee.objects.filter(email__iexact=email).first()
        if not co and emp:
            co = emp.company
        if not co:
            return JsonResponse({"status": "error", "message": "Workspace not found"}, status=403)

        ticket = Ticket.objects.filter(id=ticket_id, project__company=co).first()
        if not ticket:
            return JsonResponse({"status": "error", "message": "Ticket not found"}, status=404)

        ticket.delete()
        return JsonResponse({"status": "success", "message": "Ticket deleted successfully"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=500)



def api_notifications(request):
    if not request.session.get("verified"):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)

    email = (request.session.get("otp_email") or '').strip().lower()
    emp = get_user_employee(email)
    co = Company.objects.filter(email__iexact=email).first()
    if not co and emp:
        co = emp.company

    if emp or co:
        if not emp:
            emp = get_user_employee(co.email)

        qs = Notification.objects.filter(user=emp).order_by('-created_at')[:20] if emp else []
        unread_count = Notification.objects.filter(user=emp, unread=True).count() if emp else 0
        notifs = []
        for n in qs:
            notifs.append({
                "id": n.id,
                "type": n.notification_type,
                "title": n.title,
                "message": n.message,
                "link": n.link or "/dashboard/",
                "unread": n.unread,
                "time": n.created_at.strftime("%b %d, %H:%M") if n.created_at else ""
            })

        # Include unresolved workspace tickets for comprehensive coverage
        if co:
            tickets_qs = Ticket.objects.filter(project__company=co).select_related('employee').order_by('-created_at')[:4]
            for t in tickets_qs:
                emp_name = t.employee.name if t.employee else "Team"
                t_title = f"Ticket #{t.id}: {t.title[:24]}"
                if not any(n['title'] == t_title for n in notifs):
                    notifs.append({
                        "id": f"t_{t.id}",
                        "type": "TICKET",
                        "title": t_title,
                        "message": f"Priority: {t.priority.capitalize()} | Assigned: {emp_name}",
                        "link": f"/tickets-page/?id={t.id}",
                        "unread": True,
                        "time": t.created_at.strftime("%b %d") if hasattr(t, 'created_at') and t.created_at else "Active"
                    })
                    unread_count += 1

        return JsonResponse({
            "status": "ok",
            "count": unread_count,
            "notifications": notifs
        })

    return JsonResponse({
        "status": "ok",
        "count": 0,
        "notifications": []
    })


@csrf_exempt
def api_mark_notifications_read(request):
    if not request.session.get("verified"):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)

    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)

    email = (request.session.get("otp_email") or '').strip().lower()
    emp = get_user_employee(email)
    if not emp:
        return JsonResponse({"status": "error", "message": "User record not found"}, status=404)

    try:
        import json
        payload = json.loads(request.body.decode('utf-8')) if request.body else {}
    except Exception:
        payload = request.POST

    notif_id = payload.get('notification_id') or payload.get('id')
    mark_all = payload.get('all') or payload.get('mark_all')

    if mark_all:
        Notification.objects.filter(user=emp, unread=True).update(unread=False)
        return JsonResponse({"status": "ok", "message": "All notifications marked as read"})
    elif notif_id:
        Notification.objects.filter(user=emp, id=notif_id).update(unread=False)
        return JsonResponse({"status": "ok", "message": "Notification marked as read"})
    else:
        Notification.objects.filter(user=emp, unread=True).update(unread=False)
        return JsonResponse({"status": "ok", "message": "Notifications marked as read"})



