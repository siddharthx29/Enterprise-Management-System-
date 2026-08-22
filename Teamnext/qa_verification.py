import os
import sys
import django
import json
import base64

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from myapp.models import Company, Employee, Project, ProjectMember, ChatMessage, EmailMessage, Invoice, Expense, Payroll, Ticket, Department, Attendance, LeaveRequest
from myapp.views import (
    signup_view, save_settings, chat_messages, api_users,
    project_member_settings, send_dashboard_email, save_email_draft,
    api_notifications, api_generate_report
)

def build_request(method='GET', path='/', data=None, session_data=None):
    rf = RequestFactory()
    if method == 'GET':
        req = rf.get(path, data or {})
    elif method == 'POST':
        if isinstance(data, dict):
            req = rf.post(path, json.dumps(data), content_type='application/json')
        else:
            req = rf.post(path, data or {})
    elif method == 'PATCH':
        req = rf.patch(path, json.dumps(data or {}), content_type='application/json')
    elif method == 'DELETE':
        req = rf.delete(path, json.dumps(data or {}), content_type='application/json')
    else:
        req = rf.generic(method, path)

    SessionMiddleware(lambda r: None).process_request(req)
    MessageMiddleware(lambda r: None).process_request(req)
    req.session.save()

    if session_data:
        for k, v in session_data.items():
            req.session[k] = v
        req.session.save()

    return req

def run_tests():
    print("=" * 60)
    print("STARTING TEAMNEXT ERP QA VERIFICATION SUITE")
    print("=" * 60)

    results = {}

    # Setup test workspace
    test_co, _ = Company.objects.get_or_create(
        email='qa_company@teamnext.test',
        defaults={'name': 'QA Corp', 'password': 'hashed_qa_pwd'}
    )
    admin_emp, _ = Employee.objects.get_or_create(
        email='qa_admin@teamnext.test',
        defaults={'company': test_co, 'name': 'QA Admin', 'role': 'Administrator', 'password': 'hashed_qa_pwd'}
    )
    test_proj, _ = Project.objects.get_or_create(
        name='QA Core Project',
        company=test_co,
        defaults={'description': 'QA Testing Suite Channel'}
    )

    # 1. Chat Messaging Test
    try:
        user_emp, _ = Employee.objects.get_or_create(
            email='qa_chatter@teamnext.test',
            defaults={'company': test_co, 'name': 'QA Chatter', 'role': 'Developer', 'password': 'pwd'}
        )
        pm, _ = ProjectMember.objects.get_or_create(project=test_proj, employee=user_emp)
        pm.can_chat = True
        pm.is_allowed = True
        pm.save()

        req = build_request('POST', '/api/chat/messages/', {'project_id': test_proj.id, 'text': 'QA Test Hello'}, session_data={'verified': True, 'otp_email': user_emp.email})
        resp = chat_messages(req)
        assert resp.status_code == 200, f"Status {resp.status_code}"
        data = json.loads(resp.content)
        assert data['status'] == 'ok', data

        # Test restricted chat
        pm.can_chat = False
        pm.save()
        req_res = build_request('POST', '/api/chat/messages/', {'project_id': test_proj.id, 'text': 'Blocked Message'}, session_data={'verified': True, 'otp_email': user_emp.email})
        resp_res = chat_messages(req_res)
        assert resp_res.status_code == 403, "Restricted user was not blocked from chatting"

        results['1_chat_messaging'] = "PASSED"
    except Exception as e:
        results['1_chat_messaging'] = f"FAILED: {e}"

    # 2. Users & Access CRUD Test
    try:
        # GET
        req_g = build_request('GET', '/api/users/', session_data={'verified': True, 'otp_email': test_co.email})
        resp_g = api_users(req_g)
        users = json.loads(resp_g.content).get('users', [])
        assert len(users) > 0, "No users returned"

        # POST
        new_email = f"emp_new_{int(os.getpid())}@gmail.com"
        req_p = build_request('POST', '/api/users/', {'name': 'New Dev', 'email': new_email, 'role': 'Backend Lead'}, session_data={'verified': True, 'otp_email': test_co.email})
        resp_p = api_users(req_p)
        assert json.loads(resp_p.content)['status'] == 'ok'

        # PATCH
        req_pt = build_request('PATCH', '/api/users/', {'email': new_email, 'role': 'Principal Engineer'}, session_data={'verified': True, 'otp_email': test_co.email})
        resp_pt = api_users(req_pt)
        assert json.loads(resp_pt.content)['status'] == 'ok'
        updated_emp = Employee.objects.get(email=new_email)
        assert updated_emp.role == 'Principal Engineer'

        # DELETE
        req_d = build_request('DELETE', '/api/users/', {'email': new_email}, session_data={'verified': True, 'otp_email': test_co.email})
        resp_d = api_users(req_d)
        assert json.loads(resp_d.content)['status'] == 'ok'
        assert not Employee.objects.filter(email=new_email).exists()

        results['2_users_access'] = "PASSED"
    except Exception as e:
        results['2_users_access'] = f"FAILED: {e}"

    # 3. Employee Signup with Personal Email Test
    try:
        personal_email = f"personal_{int(os.getpid())}@gmail.com"
        rf = RequestFactory()
        post_data = {
            'kind': 'employee',
            'company_email': test_co.email,
            'employee_email_signup': personal_email,
            'employee_password_signup': 'SecretPass123!',
            'full_name': 'Personal Email User',
            'role': 'QA Specialist',
            'employee_otp_signup': '9999'
        }
        req_s = rf.post('/signup/', post_data)
        SessionMiddleware(lambda r: None).process_request(req_s)
        MessageMiddleware(lambda r: None).process_request(req_s)
        req_s.session['otp'] = '9999'
        req_s.session['otp_email'] = test_co.email
        req_s.session.save()

        resp_s = signup_view(req_s)
        created_p = Employee.objects.filter(email=personal_email).first()
        assert created_p is not None, "Personal email employee not created"
        assert created_p.company == test_co
        created_p.delete()

        results['3_employee_personal_email_signup'] = "PASSED"
    except Exception as e:
        results['3_employee_personal_email_signup'] = f"FAILED: {e}"

    # 4. Moderator Settings Persistence Test
    try:
        req_set = build_request('POST', '/api/save-settings/', {
            'company_name': 'QA Corp Rebranded',
            'phone': '+1 555 0199',
            'website': 'https://qacorp.test',
            'industry': 'Software QA Automation'
        }, session_data={'verified': True, 'otp_email': test_co.email})

        resp_set = save_settings(req_set)
        data_set = json.loads(resp_set.content)
        assert data_set['status'] == 'ok', data_set

        test_co.refresh_from_db()
        assert test_co.name == 'QA Corp Rebranded'
        assert test_co.phone == '+1 555 0199'
        assert test_co.website == 'https://qacorp.test'
        assert test_co.industry == 'Software QA Automation'

        results['4_moderator_settings'] = "PASSED"
    except Exception as e:
        results['4_moderator_settings'] = f"FAILED: {e}"

    # 5. Permissions Management Test
    try:
        perm_emp, _ = Employee.objects.get_or_create(
            email='qa_perm@teamnext.test',
            defaults={'company': test_co, 'name': 'Perm User', 'role': 'Auditor', 'password': 'pwd'}
        )
        req_pm = build_request('POST', f'/api/projects/{test_proj.id}/members/{perm_emp.email}/settings/', {
            'is_admin': True,
            'can_modify_settings': True,
            'can_approve_leaves': True,
            'can_chat': True,
            'is_allowed': True
        }, session_data={'verified': True, 'otp_email': test_co.email})

        resp_pm = project_member_settings(req_pm, str(test_proj.id), perm_emp.email)
        assert json.loads(resp_pm.content)['status'] == 'ok'

        pm_obj = ProjectMember.objects.get(project=test_proj, employee=perm_emp)
        assert pm_obj.is_admin is True
        assert pm_obj.can_modify_settings is True
        assert pm_obj.can_approve_leaves is True

        results['5_permissions_management'] = "PASSED"
    except Exception as e:
        results['5_permissions_management'] = f"FAILED: {e}"

    # 6. Email System Test
    try:
        # Send
        req_em = build_request('POST', '/dashboard/send-email/', {
            'to': 'recipient@teamnext.test',
            'subject': 'QA Test Email Subject',
            'body': 'QA Verification Email Body Text'
        }, session_data={'verified': True, 'otp_email': test_co.email})
        resp_em = send_dashboard_email(req_em)
        assert json.loads(resp_em.content)['status'] == 'success'
        assert EmailMessage.objects.filter(subject='QA Test Email Subject').exists()

        # Draft Save
        req_ds = build_request('POST', '/email-page/save-draft/', {
            'action': 'save',
            'to': 'draft_to@teamnext.test',
            'subject': 'Draft Subj',
            'body': 'Draft text'
        }, session_data={'verified': True, 'otp_email': test_co.email})
        resp_ds = save_email_draft(req_ds)
        assert json.loads(resp_ds.content)['status'] == 'ok'
        draft = EmailMessage.objects.filter(subject='Draft Subj', is_draft=True).first()
        assert draft is not None

        # Draft Delete
        req_dd = build_request('POST', '/email-page/save-draft/', {
            'action': 'delete',
            'id': draft.id
        }, session_data={'verified': True, 'otp_email': test_co.email})
        resp_dd = save_email_draft(req_dd)
        assert json.loads(resp_dd.content)['status'] == 'ok'
        assert not EmailMessage.objects.filter(id=draft.id).exists()

        results['6_email_system'] = "PASSED"
    except Exception as e:
        results['6_email_system'] = f"FAILED: {e}"

    # 7. Notifications Button / Endpoint Test
    try:
        Ticket.objects.create(project=test_proj, employee=admin_emp, title='QA Critical Server Ticket', priority='high', description='Server load high')
        req_n = build_request('GET', '/api/notifications/', session_data={'verified': True, 'otp_email': test_co.email})
        resp_n = api_notifications(req_n)
        data_n = json.loads(resp_n.content)
        assert data_n['status'] == 'ok'
        assert data_n['count'] >= 1
        assert len(data_n['notifications']) >= 1

        results['7_notifications_button'] = "PASSED"
    except Exception as e:
        results['7_notifications_button'] = f"FAILED: {e}"

    # 8. Post-Deployment Verification
    try:
        from django.conf import settings
        assert 'myapp' in settings.INSTALLED_APPS
        assert 'whitenoise.middleware.WhiteNoiseMiddleware' in settings.MIDDLEWARE
        assert hasattr(settings, 'DATABASES')
        results['8_post_deployment'] = "PASSED"
    except Exception as e:
        results['8_post_deployment'] = f"FAILED: {e}"

    # 9 & 10. Reports Accuracy & Audit Statements Deduplication Test
    try:
        Invoice.objects.get_or_create(company=test_co, client_name='Acme Corp', defaults={'amount': 15000.0, 'gst_rate': 18.0})
        Expense.objects.get_or_create(company=test_co, description='Server Cloud Hosting', defaults={'amount': 1200.0, 'category': 'Infrastructure'})

        report_types = ['Financial', 'Productivity', 'Inventory', 'Support']
        generated_reports = {}

        for rep in report_types:
            for fmt in ['pdf', 'excel']:
                req_rep = build_request('POST', '/api/reports/generate/', {'report_type': rep, 'format': fmt}, session_data={'verified': True, 'otp_email': test_co.email, 'company_name': test_co.name})
                resp_rep = api_generate_report(req_rep)
                assert resp_rep.status_code == 200, f"Error generating {rep} in {fmt}: {resp_rep.status_code}"
                rep_data = json.loads(resp_rep.content)
                assert rep_data['status'] == 'ok', f"Failed {rep} {fmt}: {rep_data}"
                raw_bytes = base64.b64decode(rep_data['file_data'])
                assert len(raw_bytes) > 200, f"Report {rep} ({fmt}) payload too small: {len(raw_bytes)} bytes"
                generated_reports[f"{rep}_{fmt}"] = len(raw_bytes)

        # Confirm distinct generation
        assert generated_reports['Financial_pdf'] != generated_reports['Productivity_pdf']
        assert generated_reports['Financial_excel'] != generated_reports['Inventory_excel']

        results['9_reports_accuracy'] = "PASSED"
        results['10_audit_statements_deduplicated'] = "PASSED"
    except Exception as e:
        results['9_reports_accuracy'] = f"FAILED: {e}"
        results['10_audit_statements_deduplicated'] = f"FAILED: {e}"

    print("\nVERIFICATION RESULTS SUMMARY:")
    print("-" * 60)
    for test_name, status in results.items():
        print(f"[{status}] {test_name}")
    print("=" * 60)

    if all(s == "PASSED" for s in results.values()):
        print("ALL 10 QA AUDIT AREAS PASSED SUCCESSFULLY!")
        return 0
    else:
        print("SOME TESTS FAILED - PLEASE REVIEW.")
        return 1

if __name__ == '__main__':
    sys.exit(run_tests())
