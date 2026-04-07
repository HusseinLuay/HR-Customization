# Copyright (c) 2026, hussain luay and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from collections import defaultdict


def execute(filters=None):
	"""Return columns and data for the report.

	This is the main entry point for the report. It accepts the filters as a
	dictionary and should return columns and data. It is called by the framework
	every time the report is refreshed or a filter is updated.
	"""
	columns = get_columns()
	data = get_data(filters)

	return columns, data


def get_columns() -> list[dict]:
	"""Return columns for the report.

	One field definition per column, just like a DocType field definition.
	"""
	return [
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
		},
		{
			"fieldname":"employee_name",
			"label": _("Employee Name"),
			"fieldtype": "Data",
		},
		{
			"fieldname":"company",
			"label": _("Company"),
			"fieldtype": "Link",
			"options": "Company",
		},
		{
			"fieldname":"month",
			"label": _("Month"),
			"fieldtype": "Int",
		},
		{
			"fieldname":"year",
			"label": _("Year"),
			"fieldtype": "Int",
		},
		{
			"fieldname":"rejected_warning_count",
			"label": _("Rejected Warnings Count"),
			"fieldtype": "Int",
		},
		{
			"fieldname":"escalation_threshold",
			"label": _("Escalation Threshold"),
			"fieldtype": "Int",	
		},
		{
			"fieldname": "threshold_exceeded",
			"label": _("Threshold Exceeded"),
			"fieldtype": "Data",
		},
		{
			"fieldname":"escalation_action_exists",
			"label": _("Escalation Action Exists"),
			"fieldtype": "Data",
		},
		{
			"fieldname":"escalation_status",
			"label": _("Escalation Status"),
			"fieldtype": "Data",
		},
		{
			"fieldname":"escalation_date",
			"label": _("Escalation Date"),
			"fieldtype": "Date",
		}
	]

def get_data(filters) -> list[list]:
	"""Return data for the report.

	The report data is a list of rows, with each row being a list of cell values.
	"""
 
	result = [] 
 
	esc_threshold = frappe.db.get_single_value("HR Custom Settings", "escalation_rejection_limit")
 
 
 
#  -----------------------------------------warnings---------------------------------------
	warnings_filters = {
		"status": "Rejected",
		"docstatus": ["<" , 2]
	}
 
	if filters.get("company"):
		warnings_filters["company"] = filters.get("company")
  
	if filters.get("employee"):
		warnings_filters["employee"] = filters.get("employee")

	warnings = frappe.get_all(
		"HR Attendance Warning",
		fields=["employee", "employee_name", "company", "warning_date", "status"],
		filters=warnings_filters,
	)
 
	grouped = defaultdict(lambda: {"employee_name": "", "company": "" , "count":0})
 
	for w in warnings: 
		if not w.warning_date: 
	  		continue
	   
		if filters.get("month") and int(filters.get("month")) != w.warning_date.month:	
	  		continue
	   
		if filters.get("year") and int(filters.get("year")) != w.warning_date.year:
	  		continue

		key = (w.employee, w.warning_date.month, w.warning_date.year)
		grouped[key]["employee_name"] = w.employee_name
		grouped[key]["company"] = w.company
		grouped[key]["count"] += 1
 #  -----------------------------------------------------------------------------------------
 
	
	for (employee, month , year ) , rejected_warning_info in grouped.items():
	 
		threshold_exceeded = "Yes" if rejected_warning_info["count"] >= esc_threshold else "No"

		escalation_filters = {
			"employee": employee,
			"month": ["between", [f"{year}-{month:02d}-01", f"{year}-{month:02d}-31"]]
		}
	
		escalation_action_exists = frappe.db.exists(
		"HR Attendance Escalation Action",
		escalation_filters
		)
  
	
		escalation_status = "N/A"
		escalation_date = None

		if threshold_exceeded == "Yes" and escalation_action_exists:
			escalation = frappe.db.get_value(
				"HR Attendance Escalation Action",
				escalation_filters,
				["status", "escalation_date"],
				as_dict=True
			)
   
			escalation_status = escalation.status
			escalation_date = escalation.escalation_date
   
		result.append({
			"employee"                : employee,
			"employee_name"           : rejected_warning_info["employee_name"],
			"company"                 : rejected_warning_info["company"],
			"month"                   : month,
			"year"                    : year,
			"rejected_warning_count"  : rejected_warning_info["count"],
			"escalation_threshold"    : esc_threshold,
			"threshold_exceeded"      : threshold_exceeded,
			"escalation_action_exists": "Yes" if escalation_action_exists else "No",
			"escalation_status"       : escalation_status,
			"escalation_date"         : escalation_date,
		})
	return result