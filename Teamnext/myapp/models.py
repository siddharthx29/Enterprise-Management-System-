from django.db import models

import time

class Company(models.Model):

    name = models.CharField(max_length=255)

    email = models.EmailField(unique=True)

    password = models.CharField(max_length=255)

    address = models.TextField(blank=True, null=True)

    phone = models.CharField(max_length=20, blank=True, null=True)

    website = models.URLField(blank=True, null=True)

    employees_count = models.CharField(max_length=50, blank=True, null=True)

    industry = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):

        return self.name

class Department(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.company.name})"

class Employee(models.Model):

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='employees')

    name = models.CharField(max_length=255)

    email = models.EmailField(unique=True)

    password = models.CharField(max_length=255)

    role = models.CharField(max_length=100, blank=True, null=True)

    department_old = models.CharField(max_length=100, blank=True, null=True) # Keep temporarily to migrate
    dept = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')

    phone = models.CharField(max_length=20, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):

        return f"{self.name} ({self.company.name})"

class Project(models.Model):

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='projects')
    departments = models.ManyToManyField(Department, related_name='projects')

    name = models.CharField(max_length=255)

    description = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):

        return self.name

class ProjectMember(models.Model):

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='project_memberships')

    can_chat = models.BooleanField(default=True)

    is_admin = models.BooleanField(default=False)

    can_modify_settings = models.BooleanField(default=False)

    can_approve_leaves = models.BooleanField(default=False)
    
    is_allowed = models.BooleanField(default=True)

    class Meta:

        unique_together = ('project', 'employee')

class Ticket(models.Model):

    PRIORITY_CHOICES = [

        ('high', 'High'),

        ('medium', 'Medium'),

        ('low', 'Low'),

    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tickets')

    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')

    title = models.CharField(max_length=255)

    description = models.TextField()

    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')

    created_at = models.DateTimeField(auto_now_add=True)

class ChatMessage(models.Model):

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='messages')

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='chat_messages')

    text = models.TextField()

    timestamp = models.DateTimeField(auto_now_add=True)

class EmailMessage(models.Model):

    sender_email = models.EmailField()

    recipient_email = models.EmailField()

    subject = models.CharField(max_length=255)

    body = models.TextField()

    is_draft = models.BooleanField(default=False)

    is_sent = models.BooleanField(default=True)

    timestamp = models.DateTimeField(auto_now_add=True)

class LeaveRequest(models.Model):

    STATUS_CHOICES = [

        ('pending', 'Pending'),

        ('approved', 'Approved'),

        ('rejected', 'Rejected'),

    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leaves')

    reason = models.TextField()

    start_date = models.DateField()

    end_date = models.DateField()

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    created_at = models.DateTimeField(auto_now_add=True)

class SocialItem(models.Model):

    ITEM_TYPES = [

        ('birthday', 'Birthday'),

        ('topic', 'Hot Topic'),

        ('dare', 'Daily Dare'),

    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='social_items')

    type = models.CharField(max_length=10, choices=ITEM_TYPES)

    title = models.CharField(max_length=255)

    content = models.TextField(blank=True, null=True)

    meta_info = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

class Invoice(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='invoices')
    client_name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18.0) # Standard 18% GST
    gst_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('paid', 'Paid'), ('cancelled', 'Cancelled')], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.gst_amount = (self.amount * self.gst_rate) / 100
        self.total_amount = self.amount + self.gst_amount
        super().save(*args, **kwargs)

class Expense(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='expenses')
    description = models.CharField(max_length=255)
    category = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(auto_now_add=True)

class Payroll(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='payrolls')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payroll_entries')
    base_salary = models.DecimalField(max_digits=12, decimal_places=2)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(auto_now_add=True)
    month_year = models.CharField(max_length=20) # e.g., "February 2026"

    def save(self, *args, **kwargs):
        self.net_salary = self.base_salary + self.bonus - self.deductions
        super().save(*args, **kwargs)

class VendorPayment(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='vendor_payments')
    vendor_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50)
    status = models.CharField(max_length=20, default='completed')
    date = models.DateField(auto_now_add=True)

class BankTransaction(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='bank_transactions')
    date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(max_length=10, choices=[('credit', 'Credit'), ('debit', 'Debit')])
    is_reconciled = models.BooleanField(default=False)

class InventoryItem(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='inventory_items')
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    sales_count = models.IntegerField(default=0) # To track top selling items
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Attendance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[('present', 'Present'), ('absent', 'Absent'), ('late', 'Late')], default='present')
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)

    class Meta:
        unique_together = ('employee', 'date')
