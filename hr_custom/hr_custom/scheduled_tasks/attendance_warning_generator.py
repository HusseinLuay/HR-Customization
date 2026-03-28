import frappe
from frappe import _
from datetime import datetime, timedelta


def generate_attendance_warnings():

    # get yesterday's date for processing
    today = datetime.today().date()
    
    # get yesterday date 
    # yesterday = today - timedelta(days=1)
    
    # temporary put a specific date for testing : 
    yesterday = datetime(2026, 3, 26).date()

   

  
    # Get threshold settings from HR Custom Settings doctype
    settings = frappe.get_single( "HR Custom Settings" )
    late_threshold = ( settings.late_entry_threshold_minutes or 15 )
    early_threshold = ( settings.early_exit_threshold_minutes or 15 )
    

    

  
    # Get all active employees
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=[
            "name",
            "employee_name",
            "company",
            "default_shift",
            "holiday_list",
            "user_id"
        ]
    )

    

    created = 0
    skipped = 0
    no_action = 0

    for employee in employees:
            result = process_employee_for_date(
                employee=employee,
                date=yesterday,
                late_threshold=late_threshold,
                early_threshold=early_threshold
            )

            if result == "created":
                created += 1
            elif result == "skipped":
                skipped += 1
            else:
                no_action += 1




def process_employee_for_date( employee, date, late_threshold, early_threshold ):
    if is_holiday(employee, date):
        return "no_action"

   
    if is_on_approved_leave(employee.name, date):
        return "no_action"

    
    attendance = get_attendance_record(
        employee.name,
        date
    )

    
    if not attendance:
        return create_warning_if_not_exists(
            employee=employee,
            date=date,
            warning_type="Absent",
            attendance=None,
            extra_data={}
        )

    
    in_time = attendance.get("in_time")
    out_time = attendance.get("out_time")

    
    if not in_time and not out_time:
        return create_warning_if_not_exists(
            employee=employee,
            date=date,
            warning_type="Absent",
            attendance=attendance,
            extra_data={}
        )

    
    shift_name = (
        attendance.get("shift") or
        employee.get("default_shift")
    )

    if not shift_name:
        # Cannot check times without shift
        return "no_action"

    # Get shift scheduled times
    shift = frappe.get_doc(
        "Shift Type",
        shift_name
    )

    # Convert shift times to seconds for comparison
    # shift.start_time and end_time are timedelta
    shift_start_seconds = get_timedelta_seconds(
        shift.start_time
    )
    shift_end_seconds = get_timedelta_seconds(
        shift.end_time
    )

    is_late = False
    is_early = False
    late_minutes = 0
    early_minutes = 0

    
    # Check Late Entry
    if in_time:
        actual_in_seconds = get_datetime_time_seconds(
            in_time
        )
        diff = actual_in_seconds - shift_start_seconds
        late_minutes = diff / 60

        if late_minutes > late_threshold:
            is_late = True
            frappe.log_error(
                f"{employee.employee_name} "
                f"late by {round(late_minutes, 1)} min",
                "Scheduled Job"
            )


    # Check Early Exit
    if out_time:
        actual_out_seconds = (
            get_datetime_time_seconds(out_time)
        )
        diff = shift_end_seconds - actual_out_seconds
        early_minutes = diff / 60

        if early_minutes > early_threshold:
            is_early = True
            frappe.log_error(
                f"{employee.employee_name} "
                f"early by {round(early_minutes, 1)} min",
                "Scheduled Job"
            )

   
    if is_late and is_early:
        warning_type = "Late Entry and Early Exit"
    elif is_late:
        warning_type = "Late Entry"
    elif is_early:
        warning_type = "Early Exit"
    else:
        return "no_action"


    # Create warning
    extra_data = {
        "shift": shift_name,
        "scheduled_in": str(shift.start_time),
        "scheduled_out": str(shift.end_time),
        "actual_in": format_datetime_to_time(
            in_time
        ),
        "actual_out": format_datetime_to_time(
            out_time
        ),
        "late_minutes": round(late_minutes, 1),
        "early_minutes": round(early_minutes, 1)
    }

    return create_warning_if_not_exists(
        employee=employee,
        date=date,
        warning_type=warning_type,
        attendance=attendance,
        extra_data=extra_data
    )


def create_warning_if_not_exists( employee, date, warning_type, attendance, extra_data ):
    # Check duplicate
    existing = frappe.db.exists(
        "HR Attendance Warning",
        {
            "employee": employee.name,
            "warning_date": date,
            "warning_type": warning_type
        }
    )

    if existing:
        return "skipped"

    # Create new warning
    warning = frappe.new_doc("HR Attendance Warning")
    warning.employee = employee.name
    warning.employee_name = employee.employee_name
    warning.company = employee.company
    warning.warning_date = date
    warning.warning_type = warning_type
    warning.status = "Pending Justification"

    # Link attendance if exists
    if attendance:
        warning.attendance = attendance.get("name")

    # Set shift
    if extra_data.get("shift"):
        warning.shift = extra_data["shift"]

    # Set scheduled times
    if extra_data.get("scheduled_in"):
        warning.scheduled_in_time = (
            extra_data["scheduled_in"]
        )

    if extra_data.get("scheduled_out"):
        warning.scheduled_out_time = (
            extra_data["scheduled_out"]
        )

    # Set actual times
    if extra_data.get("actual_in"):
        warning.actual_in_time = (
            extra_data["actual_in"]
        )

    if extra_data.get("actual_out"):
        warning.actual_out_time = (
            extra_data["actual_out"]
        )

    warning.insert(ignore_permissions=True)
    return "created"



def get_attendance_record(employee, date):
    records = frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "attendance_date": date,
            "docstatus": 1
        },
        fields=[
            "name",
            "status",
            "in_time",
            "out_time",
            "shift",
            "working_hours"
        ],
        limit=1
    )
    return records[0] if records else None


def is_holiday(employee, date):
    holiday_list = frappe.db.get_value(
        "Employee",
        employee.name,
        "holiday_list"
    )

  
    if not holiday_list:
        holiday_list = frappe.db.get_value(
            "Company",
            employee.company,
            "default_holiday_list"
        )

    if not holiday_list:
        return False

    return bool(
        frappe.db.exists(
            "Holiday",
            {
                "parent": holiday_list,
                "holiday_date": date
            }
        )
    )


def is_on_approved_leave(employee, date):
    return bool(
        frappe.db.exists(
            "Leave Application",
            {
                "employee": employee,
                "status": "Approved",
                "from_date": ("<=", date),
                "to_date": (">=", date),
                "docstatus": 1
            }
        )
    )




def get_timedelta_seconds(td):
    if td is None:
        return 0
    if hasattr(td, 'seconds'):
        return td.seconds
    if hasattr(td, 'total_seconds'):
        return int(td.total_seconds())
    return 0


def get_datetime_time_seconds(dt_value):
    if not dt_value:
        return 0

    # Handle string datetime
    if isinstance(dt_value, str):
        try:
            # Parse full datetime string
            dt = datetime.strptime(
                str(dt_value).strip(),
                "%Y-%m-%d %H:%M:%S"
            )
            return (
                dt.hour * 3600 +
                dt.minute * 60 +
                dt.second
            )
        except ValueError:
            try:
                # Try time only string
                dt = datetime.strptime(
                    str(dt_value).strip(),
                    "%H:%M:%S"
                )
                return (
                    dt.hour * 3600 +
                    dt.minute * 60 +
                    dt.second
                )
            except ValueError:
                frappe.log_error(
                    f"Cannot parse time: {dt_value}",
                    "Time Parse Error"
                )
                return 0

    # Handle datetime object
    if hasattr(dt_value, 'hour'):
        return (
            dt_value.hour * 3600 +
            dt_value.minute * 60 +
            dt_value.second
        )

    return 0


def format_datetime_to_time(dt_value):
    if not dt_value:
        return None

    if isinstance(dt_value, str):
        try:
            dt = datetime.strptime(
                str(dt_value).strip(),
                "%Y-%m-%d %H:%M:%S"
            )
            return dt.strftime("%H:%M:%S")
        except ValueError:
            return str(dt_value)

    if hasattr(dt_value, 'strftime'):
        return dt_value.strftime("%H:%M:%S")

    return str(dt_value)