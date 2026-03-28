# Copyright (c) 2026, hussain luay and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.workflow import get_workflow


class HRAttendanceWarning(Document):
    
    def _user_has_role(self, role_or_roles):
        roles = frappe.get_roles(frappe.session.user)
        if isinstance(role_or_roles, (list, tuple, set)):
            return bool(set(role_or_roles) & set(roles))
        return role_or_roles in roles

    def _get_workflow_action(self, old_state, new_state):
        if not old_state or not new_state or old_state == new_state:
            return None

        try:
            workflow = get_workflow(self.doctype)
            if not workflow:
                return None
            
            for transition in workflow.transitions:
                if transition.state == old_state and transition.next_state == new_state:
                    return transition.action
        except:
            return None

    def before_save(self):
        if self.is_new():
            return

        db_doc = frappe.db.get_value(
            self.doctype,
            self.name,
            ["workflow_state", "approval_decision"],
            as_dict=True
        )
        
        if not db_doc:
            return

        old_workflow_state = db_doc.get("workflow_state")
        new_workflow_state = self.workflow_state
        old_approval_decision = db_doc.get("approval_decision")
        new_approval_decision = self.approval_decision
        

        # Store for later use in on_update
        self._old_workflow_state = old_workflow_state
        self._old_approval_decision = old_approval_decision

        # Method 1: Detect workflow state changes
        if old_workflow_state and new_workflow_state and old_workflow_state != new_workflow_state:
            action = self._get_workflow_action(old_workflow_state, new_workflow_state)
    
            if action:
                if hasattr(self, "before_workflow_action"):
                    self.before_workflow_action(action)
        
        # Method 2: Detect approval decision changes (fallback for non-workflow mode)
        elif old_approval_decision != new_approval_decision and new_approval_decision:
            action = None
            if new_approval_decision == "Rejected":
                action = "Reject"
            elif new_approval_decision == "Approved":
                action = "Approve"
            
            if action:
                if hasattr(self, "before_workflow_action"):
                    self.before_workflow_action(action)

    def on_update(self):
        old_workflow_state = getattr(self, "_old_workflow_state", None)
        old_approval_decision = getattr(self, "_old_approval_decision", None)
        new_workflow_state = self.workflow_state
        new_approval_decision = self.approval_decision
        
        action = None
        
        # Method 1: Detect workflow state changes
        if old_workflow_state and new_workflow_state and old_workflow_state != new_workflow_state:
            action = self._get_workflow_action(old_workflow_state, new_workflow_state)
        
        # Method 2: Detect approval decision changes (fallback for non-workflow mode)
        elif old_approval_decision != new_approval_decision and new_approval_decision:
            if new_approval_decision == "Rejected":
                action = "Reject"
            elif new_approval_decision == "Approved":
                action = "Approve"
            
        
        if action and hasattr(self, "after_workflow_action"):
            self.after_workflow_action(action)
        
        # Fallback: If _should_check_escalation flag is set, check escalation
        if getattr(self, "_should_check_escalation", False) and new_approval_decision == "Rejected":
            self.check_escalation_threshold()

    def validate(self):
        self.validate_employee()
        self.validate_duplicate()
        
        if self.approval_decision == "Rejected" and not self.is_new():
            old_doc = frappe.db.get_value(
                self.doctype,
                self.name,
                ["approval_decision"],
                as_dict=True
            )
            
            if old_doc and old_doc.get("approval_decision") != "Rejected":
                frappe.log_error(
                    f"validate: Detected rejection change for {self.name}",
                    "Escalation Debug"
                )
                self._should_check_escalation = True





    def validate_employee(self):
        if not self.employee:
            frappe.throw(_("Employee is required"))

        # Auto fetch employee name if not set
        if not self.employee_name:
            self.employee_name = frappe.db.get_value(
                "Employee",
                self.employee,
                "employee_name"
            )

        # Auto fetch company if not set
        if not self.company:
            self.company = frappe.db.get_value(
                "Employee",
                self.employee,
                "company"
            )





    def validate_duplicate(self):
        if self.is_new():
            existing = frappe.db.exists(
                "Attendance Warning",
                {
                    "employee": self.employee,
                    "warning_date": self.warning_date,
                    "warning_type": self.warning_type,
                    "name": ("!=", self.name)
                }
            )

            if existing:
                frappe.throw(
                    _(
                        "An Attendance Warning already exists for "
                        "Employee {0} on {1} for {2}"
                    ).format(
                        self.employee_name,
                        self.warning_date,
                        self.warning_type
                    )
                )





    def on_submit(self):
        self.notify_employee_new_warning()





    def before_workflow_action(self, action):

        if action == "Submit Justification":
            self.validate_justification_submission()
            # Set justification timestamp before save if not already set
            if not self.justification_date:
                self.justification_date = frappe.utils.now()
                

        elif action == "Approve":
            # Only set approval details if not already set
            if self.approval_decision != "Approved":
                if not self.approval_date:
                    self.approval_date = frappe.utils.today()
                self.approval_decision = "Approved"
                self.approver = frappe.session.user
            self.validate_approver_action()

        elif action == "Reject":
            # Only set rejection details if not already set
            if self.approval_decision != "Rejected":
                if not self.approval_date:
                    self.approval_date = frappe.utils.today()
                self.approval_decision = "Rejected"
                self.approver = frappe.session.user
            self.validate_approver_action()




    def after_workflow_action(self, action):
        
        if action == "Submit Justification":
            # Fields were already set in before_workflow_action
            # Just notify approver
            self.notify_approver_justification_submitted()

        elif action == "Approve":
            # Notify employee after approval
            self.notify_employee_decision("Approved")

        elif action == "Reject":
            # Notify employee after rejection
            self.notify_employee_decision("Rejected")
            # Check if escalation needed
            self.check_escalation_threshold()






    def validate_justification_submission(self):
        if not self.justification:
            frappe.throw(
                _(
                    "Please write your justification "
                    "before submitting"
                )
            )

        employee_user = frappe.db.get_value(
            "Employee",
            self.employee,
            "user_id"
        )

        if (frappe.session.user != employee_user
                and not self._user_has_role("HR Manager")
                and not self._user_has_role("System Manager")):
            frappe.throw(
                _(
                    "Only the employee themselves "
                    "can submit justification"
                )
            )






    def validate_approver_action(self):
        if (not self._user_has_role("HR Manager")
                and not self._user_has_role("System Manager")):
            frappe.throw(
                _(
                    "Only HR Manager can "
                    "approve or reject justifications"
                )
            )





    def check_escalation_threshold(self):
        
        # Get escalation settings
            settings = frappe.get_single(
                "HR Custom Settings"
            )
            limit = settings.escalation_rejection_limit or 3
        

        # Get current month boundaries
        today = frappe.utils.today()
        month_start = frappe.utils.get_first_day(today)

        # Count rejected warnings this month
        rejected_records = frappe.db.get_list(
            "HR Attendance Warning",
            filters={
                "employee": self.employee,
                "approval_decision": "Rejected",
                "warning_date": (
                    ">=",
                    month_start
                )
            },
            fields=["name", "approval_decision", "warning_date"]
        )
        
        rejected_count = len(rejected_records)
        

        # If limit reached create escalation
        if rejected_count >= limit:
            self.create_escalation_action(
                rejected_count,
                today
            )







    def create_escalation_action( self, rejected_count, today ):
        
        month_str = today.strftime("%Y-%m")

        # Check if escalation already exists
        existing_escalation = frappe.db.exists(
            "HR Attendance Escalation Action",
            {
                "employee": self.employee,
                "month": month_str
            }
        )

        if existing_escalation:
            return

            # Create new escalation
            escalation = frappe.new_doc(
                "HR Attendance Escalation Action"
            )
            escalation.employee = self.employee
            escalation.employee_name = self.employee_name
            escalation.month = month_str
            escalation.year = int(month_str.split('-')[0])
            escalation.rejected_warning_count = (
                rejected_count
            )
            escalation.escalation_date = frappe.utils.now()
            escalation.escalated_by = frappe.session.user
            escalation.status = "Open"
            escalation.insert(ignore_permissions=True)

           
            # Notify escalation role
            self.notify_escalation_role(escalation)

            frappe.msgprint(
                _(
                    "Escalation Action created for "
                    "Employee {0} for month {1}"
                ).format(
                    self.employee_name,
                    month_str
                ),
                alert=True
            )
        

    # ─────────────────────────────────────────
    # NOTIFICATION METHODS
    # ─────────────────────────────────────────

    def notify_employee_new_warning(self):
        employee_user = frappe.db.get_value(
            "Employee",
            self.employee,
            "user_id"
        )

        if not employee_user:
            frappe.log_error(
                f"Employee {self.employee} has no "
                f"linked user account. "
                f"Cannot send warning notification.",
                "Attendance Warning Notification"
            )
            return

        # Get employee email address
        employee_email = frappe.db.get_value("User", employee_user, "email")
        if not employee_email:
            frappe.log_error(
                f"User {employee_user} has no "
                f"email address. "
                f"Cannot send warning notification.",
                "Attendance Warning Notification"
            )
            return

        # Send in-app notification
        frappe.publish_realtime(
            event="msgprint",
            message=_(
                "You have a new Attendance Warning "
                "for {0}: {1}. "
                "Please submit your justification."
            ).format(
                self.warning_date,
                self.warning_type
            ),
            user=employee_user
        )

        # Send email notification
        frappe.sendmail(
            recipients=[employee_email],
            subject=_(
                "Attendance Warning - {0}"
            ).format(self.warning_date),
            message=_(
                """
                Dear {0},<br><br>
                You have received an attendance
                warning for <b>{1}</b>
                on <b>{2}</b>.<br><br>
                Warning Type: <b>{3}</b><br><br>
                Please log in and submit your
                justification as soon as possible.
                <br><br>
                Regards,<br>
                HR Department
                """
            ).format(
                self.employee_name,
                self.warning_type,
                self.warning_date,
                self.warning_type
            )
        )






    def notify_approver_justification_submitted(self):
        # Get all users with HR Manager role
        hr_managers = frappe.get_all(
            "Has Role",
            filters={"role": "HR Manager"},
            fields=["parent"],
            pluck="parent"
        )

        if not hr_managers:
            return

        # Get email addresses for HR managers
        hr_emails = []
        for manager in hr_managers:
            user_email = frappe.db.get_value("User", manager, "email")
            if user_email:
                hr_emails.append(user_email)

        if not hr_emails:
            return

        for manager in hr_managers:
            # Send in-app notification
            frappe.publish_realtime(
                event="msgprint",
                message=_(
                    "{0} has submitted justification "
                    "for Attendance Warning {1}. "
                    "Please review and decide."
                ).format(
                    self.employee_name,
                    self.name
                ),
                user=manager
            )

        # Send email to all HR managers
        frappe.sendmail(
            recipients=hr_emails,
            subject=_(
                "Justification Submitted - {0}"
            ).format(self.employee_name),
            message=_(
                """
                Dear HR Manager,<br><br>
                <b>{0}</b> has submitted a
                justification for their attendance
                warning on <b>{1}</b>.<br><br>
                Warning Type: <b>{2}</b><br>
                Justification: <b>{3}</b><br><br>
                Please review and approve
                or reject the justification.
                <br><br>
                Regards,<br>
                System
                """
            ).format(
                self.employee_name,
                self.warning_date,
                self.warning_type,
                self.justification
            )
        )

    def notify_employee_decision(self, decision):
        employee_user = frappe.db.get_value(
            "Employee",
            self.employee,
            "user_id"
        )

        if not employee_user:
            return

        # Get employee email address
        employee_email = frappe.db.get_value("User", employee_user, "email")
        if not employee_email:
            return

        # Send in-app notification
        frappe.publish_realtime(
            event="msgprint",
            message=_(
                "Your justification for "
                "Attendance Warning on {0} "
                "has been {1}."
            ).format(
                self.warning_date,
                decision
            ),
            user=employee_user
        )

        # Send email
        frappe.sendmail(
            recipients=[employee_email],
            subject=_(
                "Attendance Warning {0} - {1}"
            ).format(
                self.name,
                decision
            ),
            message=_(
                """
                Dear {0},<br><br>
                Your justification for the
                attendance warning on <b>{1}</b>
                has been <b>{2}</b>.<br><br>
                Remarks: {3}<br><br>
                Regards,<br>
                HR Department
                """
            ).format(
                self.employee_name,
                self.warning_date,
                decision,
                self.approval_remarks or "None"
            )
        )






    def notify_escalation_role(self, escalation):
        
            settings = frappe.get_single(
                "HR Custom Settings"
            )
        
            
        escalation_role = (
            settings.escalation_role
            or "HR Manager"
        )

        # Get all users with escalation role
        escalation_users = frappe.get_all(
            "Has Role",
            filters={"role": escalation_role},
            fields=["parent"],
            pluck="parent"
        )

        if not escalation_users:
            return

        # Get email addresses for escalation users
        escalation_emails = []
        for user in escalation_users:
            user_email = frappe.db.get_value("User", user, "email")
            if user_email:
                escalation_emails.append(user_email)

        if not escalation_emails:
            return

        frappe.sendmail(
            recipients=escalation_emails,
            subject=_(
                "Attendance Escalation - {0}"
            ).format(self.employee_name),
            message=_(
                """
                Dear {0} Team,<br><br>
                An attendance escalation has been
                triggered for employee
                <b>{1}</b>.<br><br>
                Month: <b>{2}</b><br>
                Rejected Warnings: <b>{3}</b><br>
                <br>
                Please review and take
                appropriate action.
                <br><br>
                Regards,<br>
                System
                """
            ).format(
                escalation_role,
                self.employee_name,
                escalation.month,
                escalation.rejected_warning_count
            )
        )
