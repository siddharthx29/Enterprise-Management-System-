import random
import time

from datetime import timedelta, datetime

from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count, Avg, F
from django.utils import timezone

from .brevo_helper import send_brevo_email
from .models import (
    Company, Employee, Project, ProjectMember, Ticket, ChatMessage,
    EmailMessage, LeaveRequest, SocialItem, Department,
    Invoice, Expense, Payroll, VendorPayment, BankTransaction,
    InventoryItem, Attendance
)


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

        # Support multiple emails separated by comma
        email_list = [e.strip() for e in email_input.split(',') if e.strip()]
        
        # We check if at least one email exists in the system if it's for login
        if purpose in ('login', 'password_reset'):
            exists = False
            for email in email_list:
                if Company.objects.filter(email=email).exists() or Employee.objects.filter(email=email).exists():
                    exists = True
                    break
            
            if not exists:
                messages.error(request, f'None of these emails are registered.')
                return redirect('login')

        otp = str(random.randint(1000, 9999))
        request.session["otp"] = otp
        request.session["otp_email"] = email_list[0] if email_list else email_input
        request.session["otp_expiry"] = time.time() + 300 # Increased to 5 mins

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

        if not email and not target_email:

            return JsonResponse({'status': 'error', 'message': 'Email required'})

        if email and (Company.objects.filter(email=email).exists() or Employee.objects.filter(email=email).exists()):

            return JsonResponse({'status': 'error', 'message': 'Account already exists'})

        verification_email = target_email if target_email else email

        otp = str(random.randint(1000, 9999))

        request.session["otp"] = otp

        request.session["otp_email"] = verification_email

        request.session["otp_expiry"] = time.time() + 300

        request.session["otp_action"] = 'signup'

        if target_email != email:

            if not Company.objects.filter(email=target_email).exists():

                return JsonResponse({'status': 'error', 'message': 'Company with this email does not exist.'})

            msg = f"Hello,\n\nEmployee Registration Request:\nUser: {email}\nTarget Company: {target_email}\n\nVerification OTP: {otp}\n\nThis code has been sent to the company admin for verification."

            recipients = [target_email]

        else:

            msg = f"Hello,\n\nYour OTP for account verification is: {otp}\n\nExpires in 5 minutes."

            recipients = [email]

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
            to_emails=recipients,
            subject="Verify Your Account - TeamNext Enterprise Management Tool",
            html_content=html,
            plain_text=msg
        )

        return JsonResponse({'status': 'ok'})

    except Exception as e:

        return JsonResponse({'status': 'error', 'message': str(e)})

def verify_otp(request):

    if request.method != "POST":

        return redirect("login")

    user_otp = request.POST.get("otp")

    saved_otp = request.session.get("otp")

    expiry = request.session.get("otp_expiry")

    if not saved_otp or not expiry:
        print(f"DEBUG: verify_otp session check failed. saved_otp: {saved_otp}, expiry: {expiry}")
        messages.error(request, "Session expired or invalid. Please login again.")
        return redirect("login")

    if time.time() > expiry:

        messages.error(request, "OTP expired. Please request a new one.")

        return redirect("otp")

    if user_otp == saved_otp:

        action = request.session.get('otp_action')

        if action == 'signup':

            messages.error(request, "Please use the signup form to complete registration.")

            return redirect("login")

        elif action == 'password_reset':

            request.session['password_reset_email'] = request.session.get('otp_email')

            request.session.pop('otp', None)

            request.session.pop('otp_action', None)

            request.session.pop('otp_expiry', None)

            return redirect('set_password')

        request.session["verified"] = True

        email = request.session.get("otp_email")

        name = email

        company_name = "TeamNext"

        co = Company.objects.filter(email=email).first()

        if co:

            name = co.name

            company_name = co.name

        else:

            emp = Employee.objects.filter(email=email).first()

            if emp:

                name = emp.name

                company_name = emp.company.name

        request.session['company_name'] = company_name

        messages.success(request, f"Welcome back, {name}!")

        return redirect("dashboard")

    else:

        # Invalid OTP — automatically generate and send a new one
        email = request.session.get("otp_email")
        count = request.session.get("resend_count", 0)

        if email and count < 3:
            new_otp = str(random.randint(1000, 9999))
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
                messages.error(request, "Invalid OTP. Failed to send new code — please resend manually.")
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

    otp = str(random.randint(1000, 9999))

    request.session["otp"] = otp

    request.session["otp_expiry"] = time.time() + 300

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
        print(f"RESEND OTP ERROR: {str(e)}")
        messages.error(request, f"Failed to resend OTP: {str(e)}")

    return redirect("otp")

@csrf_exempt

def password_login(request):

    if request.method != 'POST':

        return redirect('login')

    email = (request.POST.get('email') or '').strip().lower()

    password = request.POST.get('password')

    if not email or not password:

        messages.error(request, 'Email and password required')

        return redirect('login')

    co = Company.objects.filter(email=email, password=password).first()

    if co:

        request.session['verified'] = True

        request.session['otp_email'] = email

        request.session['company_name'] = co.name

        messages.success(request, 'Company login successful')

        return redirect('dashboard')

    emp = Employee.objects.filter(email=email, password=password).first()

    if emp:

        request.session['verified'] = True

        request.session['otp_email'] = email

        request.session['company_name'] = emp.company.name

        messages.success(request, 'Employee login successful')

        return redirect('dashboard')

    messages.error(request, 'Invalid credentials')

    return redirect('login')

@csrf_exempt

def signup_view(request):

    if request.method == 'POST':

        kind = request.POST.get('kind')

        if kind == 'company':

            company_name = request.POST.get('company_name')

            email = (request.POST.get('company_email_signup') or '').strip().lower()

            password = request.POST.get('company_password_signup')

            if not company_name or not email or not password:

                messages.error(request, 'Company name, email and password are required')

                return redirect('login')

            if Company.objects.filter(email=email).exists() or Employee.objects.filter(email=email).exists():

                messages.error(request, 'Account already exists with this email.')

                return redirect('login')

            otp_input = request.POST.get('company_otp_signup')

            if otp_input != request.session.get('otp') or email != request.session.get('otp_email'):

                messages.error(request, 'Invalid or missing OTP.')

                return redirect('login')

            co = Company.objects.create(

                name=company_name,

                email=email,

                password=password,

                address=request.POST.get('address'),

                phone=request.POST.get('phone'),

                website=request.POST.get('website'),

                employees_count=request.POST.get('employees_count'),

                industry=request.POST.get('industry')

            )

            request.session['verified'] = True

            request.session['otp_email'] = email

            request.session['company_name'] = co.name

            request.session.pop('otp', None)

            messages.success(request, 'Workspace registered successfully!')

            return redirect('dashboard')

        elif kind == 'employee':

            email = (request.POST.get('employee_email_signup') or '').strip().lower()

            company_email = (request.POST.get('company_email') or '').strip().lower()

            try:

                company = Company.objects.get(email=company_email)

            except Company.DoesNotExist:

                messages.error(request, 'Company email does not exist.')

                return redirect('login')

            if Company.objects.filter(email=email).exists() or Employee.objects.filter(email=email).exists():

                messages.error(request, 'Account already exists.')

                return redirect('login')

            otp_input = request.POST.get('employee_otp_signup')

            if otp_input != request.session.get('otp') or company_email != request.session.get('otp_email'):

                messages.error(request, 'Invalid OTP.')

                return redirect('login')

            emp = Employee.objects.create(
                company=company,
                name=request.POST.get('full_name'),
                email=email,
                password=request.POST.get('employee_password_signup'),
                role=request.POST.get('role'),
                department_old=request.POST.get('department'),
                phone=request.POST.get('phone')
            )

            request.session['verified'] = True

            request.session['otp_email'] = email

            request.session['company_name'] = company.name

            request.session.pop('otp', None)

            messages.success(request, 'Employee registered successfully!')

            return redirect('dashboard')

        else:

             messages.error(request, 'Invalid signup kind')

             return redirect('login')

    return render(request, "login.html")

def _send_signup_otp(request, email):

    otp = str(random.randint(1000, 9999))

    request.session["otp"] = otp

    request.session["otp_email"] = email

    request.session["otp_expiry"] = time.time() + 300

    request.session["otp_action"] = 'signup'

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

        if not pwd or not email:

            messages.error(request, 'Missing info')

            return redirect('login')

        email = (email or '').strip().lower()

        co = Company.objects.filter(email=email).first()

        if co:

            co.password = pwd

            co.save()

        else:

            emp = Employee.objects.filter(email=email).first()

            if emp:

                emp.password = pwd

                emp.save()

            else:

                messages.error(request, 'User not found.')

                return redirect('login')

        request.session.pop('password_reset_email', None)

        request.session['verified'] = True

        company_name = "TeamNext"

        if co:

            company_name = co.name

        elif emp:

            company_name = emp.company.name

        request.session['company_name'] = company_name

        request.session['otp_email'] = email

        messages.success(request, 'Password set. Logged in.')

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

    email = request.session.get("otp_email")

    is_new_user = not request.session.get("has_logged_in_before", False)

    request.session["has_logged_in_before"] = True

    projects = [

        {"id": "proj_mobile", "name": "Mobile App Redesign"},

        {"id": "proj_web", "name": "Website Revamp"},

        {"id": "proj_api", "name": "Public API Launch"}

    ]

    company_name = request.session.get("company_name")

    co = Company.objects.filter(email=email).first()

    emp = Employee.objects.filter(email=email).first()

    if not co and emp:

        co = emp.company

    if not co:

        messages.error(request, "Workspace not found.")

        return redirect('login')

    is_company_admin = (Company.objects.filter(email=email).exists())

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

    email = request.session.get('otp_email')

    co = Company.objects.filter(email=email).first()

    emp = Employee.objects.filter(email=email).first()

    user_info = {

        'email': email,

        'name': co.name if co else (emp.name if emp else email),

        'role': 'Company Admin' if co else (emp.role if emp else 'Employee'),

        'company_name': co.name if co else (emp.company.name if emp else 'TeamNext'),

        'is_admin': co is not None

    }

    return render(request, 'profile_page.html', {

        'user': user_info,

        'company_name': user_info['company_name'],

        'email': email

    })

def social_page(request):

    if not request.session.get("verified"):

        return redirect("login")

    email = request.session.get('otp_email')

    co = Company.objects.filter(email=email).first()

    if not co:

        emp = Employee.objects.filter(email=email).first()

        co = emp.company if emp else None

    birthdays = SocialItem.objects.filter(company=co, type='birthday')

    topics = SocialItem.objects.filter(company=co, type='topic')

    dares = SocialItem.objects.filter(company=co, type='dare')

    return render(request, "social_page.html", {

        "email": email,

        "company_name": co.name if co else "TeamNext",

        "birthdays": birthdays,

        "hot_topics": topics,

        "dares": dares

    })

@csrf_exempt

def api_add_social_item(request):

    if request.method != "POST":

        return JsonResponse({"status": "error", "message": "Invalid method"}, status=405)

    try:

        import json

        payload = json.loads(request.body.decode("utf-8"))

        item_type = payload.get("type")

        email = request.session.get('otp_email')

        co = Company.objects.filter(email=email).first()

        if not co:

            emp = Employee.objects.filter(email=email).first()

            co = emp.company if emp else None

        if not co:

             return JsonResponse({"status": "error", "message": "Unauthorized"}, status=403)

        if item_type == "birthday":

            SocialItem.objects.create(

                company=co, type='birthday',

                title=payload.get("name"),

                meta_info=payload.get("date"),

                content=payload.get("role")

            )

        elif item_type == "topic":

            SocialItem.objects.create(

                company=co, type='topic',

                title=payload.get("title"),

                meta_info=payload.get("author"),

                content="0 comments"

            )

        elif item_type == "dare":

            SocialItem.objects.create(

                company=co, type='dare',

                title=payload.get("from"),

                meta_info=payload.get("to"),

                content=payload.get("task")

            )

        else:

            return JsonResponse({"status": "error", "message": "Unknown type"}, status=400)

        return JsonResponse({"status": "ok"})

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

        leaves_qs = LeaveRequest.objects.filter(employee__company=co)

    elif emp:

        if is_admin:

            leaves_qs = LeaveRequest.objects.filter(employee__company=emp.company)

        else:

            leaves_qs = LeaveRequest.objects.filter(employee=emp)

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

        emp = Employee.objects.filter(email=email).first()

        if not emp:

             return JsonResponse({"status": "error", "message": "Employee not found"}, status=404)

        LeaveRequest.objects.create(

            employee=emp,

            reason=data.get("reason"),

            start_date=data.get("start_date") or datetime.now().date(),

            end_date=data.get("end_date") or datetime.now().date(),

            status='pending'

        )

        return JsonResponse({"status": "ok"})

    except Exception as e:

        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@csrf_exempt

def api_leave_action(request):

    if not request.session.get("verified"):

        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=403)

    email = request.session.get("otp_email")

    co = Company.objects.filter(email=email).first()

    emp = Employee.objects.filter(email=email).first()

    is_authorized = (co is not None) or ProjectMember.objects.filter(employee=emp, can_approve_leaves=True).exists()

    if not is_authorized:

        return JsonResponse({"status": "error", "message": "Only admins can approve leaves"}, status=403)

    if request.method != "POST":

        return JsonResponse({"status": "error", "message": "Method not allowed"}, status=405)

    try:

        import json

        data = json.loads(request.body.decode("utf-8"))

        leave_id = data.get("leave_id")

        action = data.get("action")

        leave = LeaveRequest.objects.get(id=leave_id)

        if action == "approve":

            leave.status = "approved"

        elif action == "reject":

            leave.status = "rejected"

        leave.save()

        return JsonResponse({"status": "ok"})

    except LeaveRequest.DoesNotExist:

        return JsonResponse({"status": "error", "message": "Leave not found"}, status=404)

    except Exception as e:

        return JsonResponse({"status": "error", "message": str(e)}, status=500)

@csrf_exempt

def send_dashboard_email(request):

    if request.method != "POST":

        return HttpResponseBadRequest("Invalid method")

    try:

        import json

        payload = json.loads(request.body.decode("utf-8"))

        to = payload.get("to")

        subject = payload.get("subject")

        body = payload.get("body")

        if not to or not subject or not body:

            return JsonResponse({"status": "error", "message": "Missing fields"}, status=400)

        try:
            send_brevo_email(to_emails=[to], subject=subject, html_content=f"<p>{body}</p>", plain_text=body)
        except Exception as e:
            print(f"send_dashboard_email error: {e}")

        sent = request.session.get('sent_emails', [])

        sent.append({'to': to, 'subject': subject, 'body': body, 'time': int(time.time())})

        request.session['sent_emails'] = sent

        if '--teamnext' in subject:

            inbox = request.session.get('inbox', [])

            sender_email = request.session.get('otp_email', 'me')

            inbox.append({'from': sender_email, 'subject': subject, 'body': body, 'time': int(time.time())})

            request.session['inbox'] = inbox

        request.session.modified = True

        return JsonResponse({"status": "success"})

    except Exception as e:

        return JsonResponse({"status": "error", "message": str(e)}, status=500)

# Duplicate create_ticket view removed (using definition at the end of file)

def tickets_page(request):

    if not request.session.get("verified"):

        messages.error(request, "Please login to access tickets.")

        return redirect("login")

    email = request.session.get("otp_email")

    co = Company.objects.filter(email=email).first()

    emp = Employee.objects.filter(email=email).first()

    is_admin = (co is not None)

    if not co and emp:

        co = emp.company

    if not co:

        messages.error(request, "Workspace not found.")

        return redirect('login')

    if is_admin:

        projects_list = Project.objects.filter(company=co)

        tickets_list = Ticket.objects.filter(project__company=co)

    else:

        projects_list = Project.objects.filter(members__employee=emp)

        tickets_list = Ticket.objects.filter(project__in=projects_list)

    devs_qs = Employee.objects.filter(company=co)

    analytics = {

        'high': tickets_list.filter(priority='high').count(),

        'medium': tickets_list.filter(priority='medium').count(),

        'low': tickets_list.filter(priority='low').count()

    }

    recent = tickets_list.order_by('-created_at')[:20]

    return render(request, "tickets.html", {

        "tickets": tickets_list,

        "analytics": analytics,

        "recent": recent,

        "developers": [{'name': d.name, 'email': d.email} for d in devs_qs],

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

    keys_to_clear = ['verified', 'otp_email', 'otp', 'otp_expiry', 'otp_action', 'resend_count', 'pending_signup', 'password_reset_email']

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

def save_settings(request):

    if request.method != 'POST':

        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=400)

    try:

        import json

        payload = json.loads(request.body.decode('utf-8'))

        name = payload.get('company_name')

        if not name:

            return JsonResponse({'status': 'error', 'message': 'Missing company_name'}, status=400)

        request.session['company_name'] = name

        return JsonResponse({'status': 'ok', 'company_name': name})

    except Exception as e:

        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt

def chat_messages(request):

    try:

        import json

        payload = json.loads(request.body.decode('utf-8')) if request.body else {}

    except Exception:

        payload = {}

    project_id = payload.get('project') or request.GET.get('project') or payload.get('project_id')

    if not project_id:

        return JsonResponse({'status': 'error', 'message': 'Missing project id'}, status=400)

    try:

        proj = Project.objects.filter(id=project_id).first() if str(project_id).isdigit() else Project.objects.filter(name__icontains=project_id).first()

        if not proj:

            return JsonResponse({'status': 'error', 'message': 'Project not found'}, status=404)

    except Exception:

        return JsonResponse({'status': 'error', 'message': 'Error finding project'}, status=500)

    if request.method == 'GET':

        msgs_qs = ChatMessage.objects.filter(project=proj).order_by('timestamp')

        result = []
        for m in msgs_qs:
            try:
                result.append({
                    'user': m.employee.name,
                    'email': m.employee.email,
                    'text': m.text,
                    'time': int(m.timestamp.timestamp())
                })
            except Exception:
                continue

        return JsonResponse({'status': 'ok', 'messages': result})

    if request.method == 'POST':

        email = request.session.get('otp_email')

        emp = Employee.objects.filter(email=email).first()

        if not emp:
            # Check if it's a company admin
            co = Company.objects.filter(email=email).first()
            if co:
                emp, _ = Employee.objects.get_or_create(
                    email=co.email,
                    defaults={
                        'company': co,
                        'name': co.name,
                        'password': co.password,
                        'role': 'Administrator'
                    }
                )
            else:
                return JsonResponse({'status': 'error', 'message': 'Unauthorized. Please login again.'}, status=403)

        text = payload.get('text')

        if not text:

            return JsonResponse({'status': 'error', 'message': 'Empty message'}, status=400)

        msg = ChatMessage.objects.create(project=proj, employee=emp, text=text)

        return JsonResponse({'status': 'ok', 'message': {'user': emp.name, 'text': text, 'time': int(msg.timestamp.timestamp())}})

    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

def api_projects(request):

    if request.method == 'GET':

        email = request.session.get('otp_email')

        co = Company.objects.filter(email=email).first()

        is_admin = (co is not None)

        if not co:

            emp = Employee.objects.filter(email=email).first()

            if emp:

                co = emp.company

                projects_qs = Project.objects.filter(members__employee=emp)

            else:

                projects_qs = Project.objects.none()

        else:
            projects_qs = Project.objects.filter(company=co)

        result = []
        for p in projects_qs:
            dept_list = list(p.departments.values('id', 'name'))
            result.append({
                'id': p.id,
                'name': p.name,
                'desc': p.description or '',
                'departments': dept_list
            })
        return JsonResponse({'status': 'ok', 'projects': result, 'is_admin': is_admin})

    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

@csrf_exempt

def api_add_project(request):

    if request.method != 'POST':

        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    try:

        import json

        payload = json.loads(request.body.decode('utf-8'))

        name = payload.get('name')
        desc = payload.get('desc')
        dept_ids = payload.get('departments', []) # List of IDs

        if not name:

            return JsonResponse({'status': 'error', 'message': 'Name required'}, status=400)

        email = request.session.get('otp_email')

        co = Company.objects.filter(email=email).first()

        if not co:

             return JsonResponse({'status': 'error', 'message': 'Only admins can create projects'}, status=403)

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
    
    email = request.session.get('otp_email')
    co = Company.objects.filter(email=email).first()
    if not co:
        emp = Employee.objects.filter(email=email).first()
        co = emp.company if emp else None
    
    if not co:
        return JsonResponse({'status': 'error', 'message': 'Workspace not found'}, status=404)

    if request.method == 'GET':
        depts = Department.objects.filter(company=co)
        result = [{'id': d.id, 'name': d.name, 'desc': d.description or ''} for d in depts]
        return JsonResponse({'status': 'ok', 'departments': result})

    if request.method == 'POST':
        if not Company.objects.filter(email=email).exists():
            return JsonResponse({'status': 'error', 'message': 'Only admins can create departments'}, status=403)
        
        import json
        payload = json.loads(request.body.decode('utf-8'))
        name = payload.get('name')
        desc = payload.get('desc')
        if not name:
            return JsonResponse({'status': 'error', 'message': 'Name required'}, status=400)
        
        d = Department.objects.create(company=co, name=name, description=desc)
        return JsonResponse({'status': 'ok', 'department': {'id': d.id, 'name': d.name}})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

def api_users(request):

    if request.method == 'GET':

        email = request.session.get('otp_email')

        co = Company.objects.filter(email=email).first()

        if not co:

            emp = Employee.objects.filter(email=email).first()

            co = emp.company if emp else None

        if co:

            employees = Employee.objects.filter(company=co)

            result = []

            for e in employees:
                # Optimized: only show projects where they are 'is_allowed'
                assigned = list(ProjectMember.objects.filter(employee=e, is_allowed=True).values_list('project__name', flat=True))
                result.append({
                    'email': e.email,
                    'name': e.name,
                    'role': e.role,
                    'department': e.dept.name if e.dept else (e.department_old or ''),
                    'dept_id': e.dept.id if e.dept else None,
                    'phone': e.phone,
                    'projects': assigned
                })

        else:

            result = []

        return JsonResponse({'status': 'ok', 'users': result})

    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

@csrf_exempt

def project_members(request, project_id):

    if not request.session.get('verified'):

        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    email = request.session.get('otp_email')

    is_admin = Company.objects.filter(email=email).exists()

    if request.method == 'GET':

        try:

            proj = Project.objects.get(id=project_id)

            members = ProjectMember.objects.filter(project=proj)

            result = [{'name': m.employee.name, 'email': m.employee.email} for m in members]

            return JsonResponse({'status': 'ok', 'members': result})

        except Project.DoesNotExist:

            return JsonResponse({'status': 'error', 'message': 'Project not found'}, status=404)

    if request.method == 'POST':

        if not is_admin:

            return JsonResponse({'status': 'error', 'message': 'Only company admins can add/remove members'}, status=403)

        try:

            import json

            payload = json.loads(request.body.decode('utf-8'))

            member_email = payload.get('email')

            action = payload.get('action', 'add')

            if not member_email:

                return JsonResponse({'status': 'error', 'message': 'Email required'}, status=400)

            proj = Project.objects.get(id=project_id)

            emp = Employee.objects.filter(email=member_email).first()

            if not emp:

                return JsonResponse({'status': 'error', 'message': 'Employee not found'}, status=404)

            if action == 'remove':

                ProjectMember.objects.filter(project=proj, employee=emp).delete()

                return JsonResponse({'status': 'ok', 'message': 'Member removed'})

            else:

                pm, created = ProjectMember.objects.get_or_create(project=proj, employee=emp)

                return JsonResponse({'status': 'ok', 'message': 'Member added'})

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

            projects_qs = Project.objects.filter(members__employee=emp)

        else:

            projects_qs = Project.objects.none()

    else:

        projects_qs = Project.objects.filter(company=co)

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

    email = request.session.get('otp_email')

    co = Company.objects.filter(email=email).first()

    if not co:

        emp = Employee.objects.filter(email=email).first()

        co = emp.company if emp else None

    projects_qs = Project.objects.filter(company=co) if co else Project.objects.none()

    return render(request, 'chat_page.html', {

        'company_name': co.name if co else "TeamNext",

        'projects': projects_qs,

        'email': email

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

@csrf_exempt

def project_member_settings(request, project_id, member_email):

    if not request.session.get('verified'):

        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    try:

        proj = Project.objects.get(id=project_id)

        emp = Employee.objects.get(email=member_email)

        pm, created = ProjectMember.objects.get_or_create(project=proj, employee=emp)

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
            import json
            payload = json.loads(request.body.decode('utf-8'))
            pm.is_admin = bool(payload.get('is_admin', pm.is_admin))
            pm.can_modify_settings = bool(payload.get('can_modify_settings', pm.can_modify_settings))
            pm.can_approve_leaves = bool(payload.get('can_approve_leaves', pm.can_approve_leaves))
            pm.can_chat = bool(payload.get('can_chat', pm.can_chat))
            pm.is_allowed = bool(payload.get('is_allowed', pm.is_allowed))
            pm.save()
            return JsonResponse({'status': 'ok', 'settings': {'is_admin': pm.is_admin, 'is_allowed': pm.is_allowed}})

    except Exception as e:

        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

def settings_page(request):

    if not request.session.get('verified'):

        messages.error(request, 'Please login to access settings.')

        return redirect('login')

    email = request.session.get('otp_email')

    co = Company.objects.filter(email=email).first()

    if not co:

        messages.error(request, "Access Denied: Only Company Admins can view this page.")

        return redirect('dashboard')

    return render(request, 'settings_page.html', {

        'company_name': co.name,

        'email': email,

        'co_info': co

    })

@csrf_exempt

def reset_db_view(request):

    request.session.flush()

    messages.success(request, "System database reset successfully. All accounts cleared.")

    return redirect("login")

@csrf_exempt

def save_email_draft(request):

    if request.method != 'POST':

        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    try:

        import json

        payload = json.loads(request.body.decode('utf-8'))

        email = request.session.get('otp_email')

        action = payload.get('action')

        if action == 'save':

            EmailMessage.objects.create(

                sender_email=email,

                recipient_email=payload.get('to', ''),

                subject=payload.get('subject', ''),

                body=payload.get('body', ''),

                is_draft=True,

                is_sent=False

            )

            return JsonResponse({'status': 'ok'})

        if action == 'delete':

            msg_id = payload.get('id')

            EmailMessage.objects.filter(id=msg_id, sender_email=email, is_draft=True).delete()

            return JsonResponse({'status': 'ok'})

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

        email = request.session.get('otp_email')

        EmailMessage.objects.create(

            sender_email=payload.get('from', 'unknown'),

            recipient_email=email,

            subject=payload.get('subject', '(no subject)'),

            body=payload.get('body', ''),

            is_draft=False,

            is_sent=True

        )

        return JsonResponse({'status': 'ok'})

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
    email = request.session.get('otp_email')
    company_name = request.session.get('company_name', 'TeamNext')
    return render(request, 'reports_page.html', {'email': email, 'company_name': company_name})

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

        # Assuming entity is employee email or name
        # For simplicity, we'll try to find an employee
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
        if not co: return JsonResponse({'status': 'error', 'message': 'Company not found'})

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
        if not co: return JsonResponse({'status': 'error', 'message': 'Company not found'})

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
    if not co: return JsonResponse({'status': 'error', 'message': 'Access denied'})

    format = request.GET.get('format', 'csv')
    if format == 'csv':
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
    if not co: return JsonResponse({'status': 'error', 'message': 'Access denied'})

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
    if request.method == 'POST':
        import json
        import io
        from django.http import HttpResponse
        try:
            from reportlab.pdfgen import canvas
            from openpyxl import Workbook
        except ImportError:
            return JsonResponse({'status': 'error', 'message': 'PDF/Excel libraries not installed'}, status=500)

        try:
            data = json.loads(request.body)
            report_type = data.get('report_type', 'General')
            file_format = data.get('format', 'pdf')
            company_name = request.session.get('company_name', 'TeamNext')
            email = request.session.get('otp_email')
            co = Company.objects.filter(email=email).first()

            if file_format == 'pdf':
                buffer = io.BytesIO()
                p = canvas.Canvas(buffer)
                p.setFont("Helvetica-Bold", 16)
                p.drawString(100, 800, f"{company_name} - {report_type}")
                p.setFont("Helvetica", 12)
                p.drawString(100, 780, f"Generated On: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                p.line(100, 770, 500, 770)
                
                y = 740
                if report_type == 'Tax Report' and co:
                    invoices = Invoice.objects.filter(company=co)
                    total_gst = sum(inv.gst_amount for inv in invoices)
                    total_revenue = sum(inv.amount for inv in invoices)
                    
                    p.drawString(100, y, f"Total Net Revenue: ${total_revenue:,.2f}")
                    p.drawString(100, y-20, f"Total GST Collected (18% Avg): ${total_gst:,.2f}")
                    p.drawString(100, y-40, f"Total Gross Revenue: ${(total_revenue + total_gst):,.2f}")
                    y -= 80
                    p.drawString(100, y, "Recent Taxable Invoices:")
                    y -= 20
                    for inv in invoices[:10]:
                        p.drawString(120, y, f"- {inv.client_name}: ${inv.amount:,.2f} + ${inv.gst_amount:,.2f} GST")
                        y -= 15
                else:
                    p.drawString(100, y, "Summary of Operations:")
                    p.drawString(120, y-20, "- Performance Index: 94%")
                    p.drawString(120, y-40, "- Resource Utilization: 88%")
                
                p.showPage()
                p.save()
                buffer.seek(0)
                import base64
                encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
                return JsonResponse({'status': 'ok', 'message': 'Success', 'file_data': encoded, 'content_type': 'application/pdf'})

            else:  # excel logic similar to before but with real data if needed
                wb = Workbook()
                ws = wb.active
                ws.title = report_type
                ws.append([f"{company_name} {report_type} Report"])
                ws.append(["Timestamp", time.strftime('%Y-%m-%d %H:%M:%S')])
                ws.append([])
                if report_type == 'Tax Report' and co:
                    ws.append(["Client", "Net Amount", "GST Amount", "Total", "Date"])
                    for inv in Invoice.objects.filter(company=co):
                        ws.append([inv.client_name, float(inv.amount), float(inv.gst_amount), float(inv.total_amount), inv.created_at.strftime('%Y-%m-%d')])
                else:
                    ws.append(["Metric", "Value", "Status"])
                    ws.append(["Production", "1,200 units", "On Track"])
                
                buffer = io.BytesIO()
                wb.save(buffer)
                buffer.seek(0)
                import base64
                encoded = base64.b64encode(buffer.getvalue()).decode('utf-8')
                return JsonResponse({'status': 'ok', 'message': 'Success', 'file_data': encoded, 'content_type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

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
        employee = Employee.objects.create(
            company=co,
            name=data.get('name'),
            email=data.get('email'),
            password='changeme123',  # Default password
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
        description = data.get('description', 'Created from dashboard quick actions') or 'Created from dashboard quick actions'
        priority = data.get('priority', 'medium')

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

        # Try to find the project by ID; fall back to the first project in the company
        proj = None
        if project_id:
            try:
                proj = Project.objects.filter(id=int(project_id), company=co).first()
            except (ValueError, TypeError):
                proj = None

        if not proj:
            # Fall back to first available project for this workspace
            proj = Project.objects.filter(company=co).first()

        if not proj:
            return JsonResponse({'status': 'error', 'message': 'No project found. Please create a project first from the Departments page.'})

        # Ticket model only has: project, employee, title, description, priority
        Ticket.objects.create(
            project=proj,
            employee=emp if emp else None,
            title=title,
            description=description,
            priority=priority if priority in ('high', 'medium', 'low') else 'medium',
        )
        return JsonResponse({'status': 'success', 'message': f'Ticket "{title}" raised in project "{proj.name}"'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

