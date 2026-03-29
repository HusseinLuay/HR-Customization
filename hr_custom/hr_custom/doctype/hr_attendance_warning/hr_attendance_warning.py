import frappe
from frappe import _
from frappe.model.document import Document


class HRAttendanceWarning(Document):

    def validate(self):
        self.validate_employee()
        self.validate_duplicate()



    def on_submit(self):
        self._notify_employee_new_warning()
        
        
    def before_save(self):
        if self.is_new():
            return
    
        self._old_workflow_state = frappe.db.get_value(
            self.doctype,
            self.name,
            "workflow_state"
        )



    def on_update(self):
        if self.is_new():
            return

        old_state = getattr(
        self,
        '_old_workflow_state',
        None
    )

        current_state = self.workflow_state
        self.db_set('status', current_state)

        if old_state == current_state:
            return

        if current_state == "Pending Approval":
            self._handle_justification_submitted()

        elif current_state == "Approved":
            self._handle_approved()

        elif current_state == "Rejected":
            self._handle_rejected()

    
    def _has_role(self, role):
        return role in frappe.get_roles( frappe.session.user)

    def _handle_justification_submitted(self):
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
                and not self._has_role("HR Manager")
                and not self._has_role("System Manager")):
            frappe.throw(
                _(
                    "Only the employee themselves "
                    "can submit justification"
                )
            )

        if not self.justification_date:
            self.db_set(
                'justification_date',
                frappe.utils.now()
            )

        self.db_set('status', 'Pending Approval')
        self._notify_approver()



    def _handle_approved(self):
        if (not self._has_role("HR Manager")
                and not self._has_role( "System Manager")):
            frappe.throw(
                _(
                    "Only HR Manager can "
                    "approve justifications"
                )
            )

        if not self.approval_date:
            self.db_set(
                'approval_date',
                frappe.utils.now()
            )

        if not self.approver:
            self.db_set(
                'approver',
                frappe.session.user
            )

        if self.approval_decision != "Approved":
            self.db_set(
                'approval_decision',
                'Approved'
            )

        self._notify_employee_decision("Approved")

    def _handle_rejected(self):
        if (not self._has_role("HR Manager")
                and not self._has_role(
                    "System Manager"
                )):
            frappe.throw(
                _(
                    "Only HR Manager can "
                    "reject justifications"
                )
            )

        if not self.approval_date:
            self.db_set(
                'approval_date',
                frappe.utils.now()
            )

        if not self.approver:
            self.db_set(
                'approver',
                frappe.session.user
            )

        if self.approval_decision != "Rejected":
            self.db_set(
                'approval_decision',
                'Rejected'
            )

        self._notify_employee_decision("Rejected")
        self._check_escalation()



    def validate_employee(self):
        if not self.employee:
            frappe.throw(_("Employee is required"))

        if not self.employee_name:
            self.employee_name = frappe.db.get_value(
                "Employee",
                self.employee,
                "employee_name"
            )

        if not self.company:
            self.company = frappe.db.get_value(
                "Employee",
                self.employee,
                "company"
            )



    def validate_duplicate(self):
        if self.is_new():
            existing = frappe.db.exists(
                "HR Attendance Warning",
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
                        "An Attendance Warning already "
                        "exists for Employee {0} "
                        "on {1} for {2}"
                    ).format(
                        self.employee_name,
                        self.warning_date,
                        self.warning_type
                    )
                )

 

    def _check_escalation(self):
        try:
            settings = frappe.get_single( "HR Custom Settings")
            limit = ( settings.escalation_rejection_limit or 3 )
        except Exception:
            limit = 3

        today = frappe.utils.today()
        month_start = today[:7] + "-01"

        rejected_count = frappe.db.count(
            "HR Attendance Warning",
            filters={
                "employee": self.employee,
                "approval_decision": "Rejected",
                "warning_date": [">=", month_start]
            }
        )


        if rejected_count >= limit:
            self._create_escalation(
                rejected_count,
                today
            )

    def _create_escalation( self, rejected_count, today ):
        month_str = today[:7] 
        month_date = today[:7] + "-01"
        

        existing = frappe.db.exists(
            "HR Attendance Escalation Action",
            {
                "employee": self.employee,
                "month": month_date
            }
        )

        if existing:
            existing_doc = frappe.get_doc(
                "HR Attendance Escalation Action",
                existing
            )
            if rejected_count > ( existing_doc.rejected_warning_count):
                existing_doc.db_set(
                    'rejected_warning_count',
                    rejected_count
                )
            return

        # Create new escalation
        escalation = frappe.new_doc(
            "HR Attendance Escalation Action"
        )
        escalation.employee = self.employee
        escalation.employee_name = self.employee_name
        escalation.month = month_date
        escalation.year = int(today[:4])
        escalation.rejected_warning_count = (
            rejected_count
        )
        escalation.escalation_date = (
            frappe.utils.now()
        )
        escalation.escalated_by = frappe.session.user
        escalation.status = "Open"
        escalation.insert(ignore_permissions=True)


        # Notify escalation role
        self._notify_escalation_role(escalation)

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


    def _notify_employee_new_warning(self):
        employee_user = frappe.db.get_value(
            "Employee",
            self.employee,
            "user_id"
        )

        if not employee_user:
            return

        # In-app notification
        frappe.get_doc({
            "doctype": "Notification Log",
            "subject": _(
                "New Attendance Warning - {0}"
            ).format(self.warning_type),
            "email_content": _(
                "You have a new attendance warning "
                "for {0} on {1}. "
                "Please submit your justification."
            ).format(
                self.warning_type,
                self.warning_date
            ),
            "for_user": employee_user,
            "document_type": "HR Attendance Warning",
            "document_name": self.name,
            "type": "Alert"
        }).insert(ignore_permissions=True)

        # Email notification
        frappe.sendmail(
            recipients=[employee_user],
            subject=_(
                "New Attendance Warning - {0}"
            ).format(self.warning_date),
            message=frappe.render_template(
                """
                Dear {{ employee_name }},<br><br>
                You have received an attendance
                warning.<br><br>
                <b>Warning Type:</b>
                {{ warning_type }}<br>
                <b>Date:</b>
                {{ warning_date }}<br><br>
                Please log in and submit your
                justification as soon as possible.
                <br><br>
                Regards,<br>
                HR Department
                """,
                {
                    "employee_name": (
                        self.employee_name
                    ),
                    "warning_type": self.warning_type,
                    "warning_date": str(
                        self.warning_date
                    )
                }
            )
        )



    def _notify_approver(self):
        hr_managers = frappe.get_all(
            "Has Role",
            filters={
                "role": "HR Manager",
                "parenttype": "User"
                },
            pluck="parent"
        )
        
        hr_managers = [
            u for u in hr_managers
            if frappe.db.exists("User", {"name": u, "enabled": 1})
        ]

        if not hr_managers:
            return

        # In-app notification for each manager
        for manager in hr_managers:
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": _(
                    "Justification Submitted - {0}"
                ).format(self.employee_name),
                "email_content": _(
                    "{0} submitted justification "
                    "for warning on {1}. "
                    "Please review."
                ).format(
                    self.employee_name,
                    self.warning_date
                ),
                "for_user": manager,
                "document_type": (
                    "HR Attendance Warning"
                ),
                "document_name": self.name,
                "type": "Alert"
            }).insert(ignore_permissions=True)

        # Email to all HR managers
        frappe.sendmail(
            recipients=hr_managers,
            subject=_(
                "Justification Submitted - {0}"
            ).format(self.employee_name),
            message=frappe.render_template(
                """
                Dear HR Manager,<br><br>
                <b>{{ employee_name }}</b> has
                submitted a justification for
                their attendance warning on
                <b>{{ warning_date }}</b>.<br><br>
                <b>Warning Type:</b>
                {{ warning_type }}<br>
                <b>Justification:</b>
                {{ justification }}<br><br>
                Please review and approve
                or reject.
                <br><br>
                Regards,<br>
                System
                """,
                {
                    "employee_name": (
                        self.employee_name
                    ),
                    "warning_date": str(
                        self.warning_date
                    ),
                    "warning_type": self.warning_type,
                    "justification": self.justification
                }
            )
        )

    def _notify_employee_decision(self, decision):
         
        employee_user = frappe.db.get_value(
            "Employee",
            self.employee,
            "user_id"
        )

        if not employee_user:
            return

        # In-app notification
        frappe.get_doc({
            "doctype": "Notification Log",
            "subject": _(
                "Warning {0} - {1}"
            ).format(decision, self.warning_date),
            "email_content": _(
                "Your justification for warning "
                "on {0} has been {1}. "
                "Remarks: {2}"
            ).format(
                self.warning_date,
                decision,
                self.approval_remarks or "None"
            ),
            "for_user": employee_user,
            "document_type": "HR Attendance Warning",
            "document_name": self.name,
            "type": "Alert"
        }).insert(ignore_permissions=True)

        # Email notification
        frappe.sendmail(
            recipients=[employee_user],
            subject=_(
                "Attendance Warning {0} - {1}"
            ).format(self.name, decision),
            message=frappe.render_template(
                """
                Dear {{ employee_name }},<br><br>
                Your justification for attendance
                warning on <b>{{ warning_date }}</b>
                has been <b>{{ decision }}</b>.
                <br><br>
                {% if remarks %}
                <b>Remarks:</b> {{ remarks }}<br>
                {% endif %}
                <br>
                Regards,<br>
                HR Department
                """,
                {
                    "employee_name": (
                        self.employee_name
                    ),
                    "warning_date": str(
                        self.warning_date
                    ),
                    "decision": decision,
                    "remarks": (
                        self.approval_remarks or ""
                    )
                }
            )
        )

    def _notify_escalation_role(self, escalation):
        try:
            settings = frappe.get_single(
                "HR Custom Settings"
            )
            escalation_role = (
                settings.escalation_role
                or "HR Manager"
            )
        except Exception:
            escalation_role = "HR Manager"

        escalation_users = frappe.get_all(
            "Has Role",
            filters={"role": escalation_role},
            pluck="parent"
        )
        
        escalation_users = [         
            u for u in escalation_users
            if frappe.db.exists("User", {"name": u, "enabled": 1})
        ]   

        if not escalation_users:
            return

        # In-app notification for each user
        for user in escalation_users:
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": _(
                    "Attendance Escalation - {0}"
                ).format(self.employee_name),
                "email_content": _(
                    "Escalation triggered for {0} "
                    "in month {1} with {2} "
                    "rejected warnings."
                ).format(
                    self.employee_name,
                    escalation.month,
                    escalation.rejected_warning_count
                ),
                "for_user": user,
                "document_type": (
                    "HR Attendance Escalation Action"
                ),
                "document_name": escalation.name,
                "type": "Alert"
            }).insert(ignore_permissions=True)

        # Email notification
        frappe.sendmail(
            recipients=escalation_users,
            subject=_(
                "Attendance Escalation - {0}"
            ).format(self.employee_name),
            message=frappe.render_template(
                """
                Dear {{ escalation_role }} Team,
                <br><br>
                An attendance escalation has been
                triggered for employee
                <b>{{ employee_name }}</b>.<br><br>
                <b>Month:</b> {{ month }}<br>
                <b>Rejected Warnings:</b>
                {{ count }}<br><br>
                Please review and take action.
                <br><br>
                Regards,<br>
                System
                """,
                {
                    "escalation_role": escalation_role,
                    "employee_name": self.employee_name,
                    "month": escalation.month,
                    "count": (
                        escalation.rejected_warning_count
                    )
                }
            )
        )
