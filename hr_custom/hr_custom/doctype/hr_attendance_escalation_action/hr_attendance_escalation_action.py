import frappe
from frappe import _
from frappe.model.document import Document
from datetime import datetime


class HRAttendanceEscalationAction(Document):

    def validate(self):
        self.validate_action_fields()


    def validate_action_fields(self):
        if self.action == "Deduct Leave Day":
            if not self.leave_type_for_deduction:
                frappe.throw(
                    _(
                        "Please select Leave Type "
                        "for deduction"
                    )
                )

        elif self.action == "Deduct Salary Day":
            if not self.salary_component_for_deduction:
                frappe.throw(
                    _(
                        "Please select Salary Component "
                        "for deduction"
                    )
                )

    def on_submit(self):
        if not self.action:
            frappe.throw(
                _(
                    "Please select an action "
                    "before submitting"
                )
            )

        if self.action == "Deduct Leave Day":
            self.execute_leave_deduction()

        elif self.action == "Deduct Salary Day":
            self.execute_salary_deduction()

        elif self.action == "No Action":
            self.execute_no_action()

        # Update status
        self.db_set('status', 'Action Selected')

        # Notify employee
        self.notify_employee_of_action()

    def execute_leave_deduction(self):
        leave_balance = get_leave_balance(
            employee=self.employee,
            leave_type=self.leave_type_for_deduction
        )

        if leave_balance <= 0:
            frappe.msgprint(
                _(
                    "Warning: Employee {0} has no "
                    "remaining {1} balance. "
                    "Deduction will result in "
                    "negative balance."
                ).format(
                    self.employee_name,
                    self.leave_type_for_deduction
                ),
                indicator="orange"
            )

        # Create Leave ledger entry  
        today = frappe.utils.today()
        ledger = frappe.new_doc("Leave Ledger Entry")
        ledger.employee = self.employee
        ledger.employee_name = self.employee_name
        ledger.leave_type = self.leave_type_for_deduction
        ledger.transaction_type = self.doctype
        ledger.transaction_name = self.name
        ledger.leaves = -1
        ledger.from_date = today
        ledger.to_date = today
        ledger.is_carry_forward = 0
        ledger.is_expired = 0
        ledger.submit()


        frappe.msgprint(
                _(
                    "Leave deduction of 1 day "
                    "applied for {0}. "
                    "Leave Type: {1}"
                ).format(
                    self.employee_name,
                    self.leave_type_for_deduction
                ),
                indicator="green"
        )


    def execute_salary_deduction(self):
        # Get employee daily salary
        daily_amount = get_daily_salary_amount(
            self.employee
        )

        # Create Additional Salary
        # (negative amount = deduction)
        additional_salary = frappe.new_doc("Additional Salary")
        additional_salary.employee = self.employee
        additional_salary.employee_name = ( self.employee_name)
        additional_salary.salary_component = ( self.salary_component_for_deduction )
        additional_salary.amount = daily_amount
        additional_salary.payroll_date = ( frappe.utils.today() )
        additional_salary.company = frappe.db.get_value(
            "Employee",
            self.employee,
            "company"
            )
        additional_salary.notes = (
            f"Attendance Escalation Deduction - "
            f"Month: {self.month} - "
            f"Ref: {self.name}"
        )
        additional_salary.insert(
            ignore_permissions=True
        )
        additional_salary.submit()

        frappe.msgprint(
            _(
                "Salary deduction of {0} "
                "applied for {1}. "
                "Will be applied in next payroll."
            ).format(
                daily_amount,
                self.employee_name
            ),
            indicator="green"
        )


        
    def execute_no_action(self):
        frappe.msgprint(
            _(
                "No action recorded for {0}. "
                "Case closed."
            ).format(self.employee_name),
            indicator="blue"
        )

    def notify_employee_of_action(self):
        employee_user = frappe.db.get_value(
            "Employee",
            self.employee,
            "user_id"
        )

        if not employee_user:
            return

        # Prepare action message
        if self.action == "Deduct Leave Day":
            action_message = _(
                "One leave day has been deducted "
                "from your {0} balance."
            ).format(
                self.leave_type_for_deduction
            )

        elif self.action == "Deduct Salary Day":
            action_message = _(
                "One day salary deduction has been "
                "applied and will reflect in "
                "your next payslip."
            )

        else:
            action_message = _(
                "No financial action has been taken."
            )

        # System notification
        frappe.get_doc({
            "doctype": "Notification Log",
            "subject": _(
                "Attendance Escalation Decision - {0}"
            ).format(self.month),
            "email_content": frappe.render_template(
                """
                Dear {{ employee_name }},<br><br>
                Your attendance escalation for
                month <b>{{ month }}</b> has been
                reviewed.<br><br>
                <b>Decision:</b> {{ action }}<br>
                {{ action_message }}<br><br>
                <b>Rejected Warnings:</b>
                {{ rejected_count }}<br><br>
                {% if notes %}
                <b>Notes:</b> {{ notes }}<br>
                {% endif %}
                <br>
                Regards,<br>
                HR Department
                """,
                {
                    "employee_name": (
                        self.employee_name
                    ),
                    "month": self.month,
                    "action": self.action,
                    "action_message": action_message,
                    "rejected_count": (
                        self.rejected_warning_count
                    ),
                    "notes": (
                        self.action_notes or ""
                    )
                }
            ),
            "for_user": employee_user,
            "document_type": (
                "HR Attendance Escalation Action"
            ),
            "document_name": self.name,
            "type": "Alert"
        }).insert(ignore_permissions=True)

        # Email notification
        frappe.sendmail(
            recipients=[employee_user],
            subject=_(
                "Attendance Escalation Decision - {0}"
            ).format(self.month),
            message=frappe.render_template(
                """
                Dear {{ employee_name }},<br><br>
                Your attendance escalation for
                month <b>{{ month }}</b> has been
                reviewed by HR.<br><br>
                <b>Rejected Warnings:</b>
                {{ rejected_count }}<br>
                <b>Decision:</b>
                {{ action }}<br><br>
                {{ action_message }}<br><br>
                {% if notes %}
                <b>HR Notes:</b> {{ notes }}<br>
                {% endif %}
                <br>
                Regards,<br>
                HR Department
                """,
                {
                    "employee_name": (
                        self.employee_name
                    ),
                    "month": self.month,
                    "action": self.action,
                    "action_message": action_message,
                    "rejected_count": (
                        self.rejected_warning_count
                    ),
                    "notes": (
                        self.action_notes or ""
                    )
                }
            )
        )



def get_leave_balance(employee, leave_type):
    try:
        from hrms.hr.utils import get_leave_balance_on
        balance = get_leave_balance_on(
            employee=employee,
            date=frappe.utils.today(),
            leave_type=leave_type
        )
        return balance or 0
    except Exception:
        # Fallback method
        allocation = frappe.db.sql(
            """
            SELECT SUM(new_leaves_allocated)
            FROM `tabLeave Allocation`
            WHERE employee = %s
            AND leave_type = %s
            AND docstatus = 1
            """,
            (employee, leave_type)
        )
        return allocation[0][0] or 0 if allocation else 0


def get_daily_salary_amount(employee):
    try:
        # Get employee base salary
        assignment  = frappe.db.get_value(
            "Salary Structure Assignment",
            {
                "employee": employee,
                "docstatus": 1
            },
            ["base","salary_structure"],
            order_by="from_date desc"
        )

        base = float(assignment.base or 0)
        salary_structure = assignment.salary_structure
        
        earnings = frappe.get_all(
        "Salary Detail",
        filters={
            "parent": salary_structure,
            "parentfield": "earnings",
            "parenttype": "Salary Structure"
        },
        fields=[
            "salary_component",
            "amount",
            "formula",
            "amount_based_on_formula"
        ]
    )
        
        deductions = frappe.get_all(
        "Salary Detail",
        filters={
            "parent": salary_structure,
            "parentfield": "deductions",
            "parenttype": "Salary Structure"
        },
        fields=[
            "salary_component",
            "amount",
            "formula",
            "amount_based_on_formula"
        ]
    )
        
        
        total_earnings = base
        
        for earning in earnings:
            if earning.amount_based_on_formula and earning.formula:
                amount = evaluate_formula(
                earning.formula,
                base
            )
            else:
                amount = float(earning.amount or 0)
                total_earnings += amount
        
        
        total_deductions = 0
        for deduction in deductions:
            if deduction.amount_based_on_formula and deduction.formula:
                amount = evaluate_formula(
                deduction.formula,
                base
            )
            else:
                amount = float(deduction.amount or 0)
                total_deductions += amount
                
        net_pay = total_earnings - total_deductions

        # Calculate daily rate
        # Assuming 30 working days per month
        working_days = 30
        daily_amount = float(net_pay) / working_days

        return round(daily_amount, 2)

    except Exception as e:
        frappe.log_error(
            f"Could not calculate daily salary "
            f"for {employee}: {str(e)}",
            "Salary Calculation Error"
        )
        return 0
    

def evaluate_formula(formula, base):
    try:
        # Only allow safe variables
        result = frappe.safe_eval(
            formula,
            eval_locals={"base": base}
        )
        return float(result or 0)
    except Exception as e:
        frappe.log_error(
            f"Could not evaluate formula '{formula}': {str(e)}",
            "Formula Evaluation Error"
        )
        return 0
