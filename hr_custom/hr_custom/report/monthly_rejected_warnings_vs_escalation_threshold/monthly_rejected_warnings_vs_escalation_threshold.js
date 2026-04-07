// Copyright (c) 2026, hussain luay and contributors
// For license information, please see license.txt

frappe.query_reports["Monthly Rejected Warnings vs Escalation Threshold"] = {
	filters: [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
		},
		{
			"fieldname": "month",
			"label": __("Month"),
			"fieldtype": "Select",
			"options": [
				{ "value": "",   "label": __("") },
				{ "value": "1",  "label": __("January")    },
				{ "value": "2",  "label": __("February")   },
				{ "value": "3",  "label": __("March")      },
				{ "value": "4",  "label": __("April")      },
				{ "value": "5",  "label": __("May")        },
				{ "value": "6",  "label": __("June")       },
				{ "value": "7",  "label": __("July")       },
				{ "value": "8",  "label": __("August")     },
				{ "value": "9",  "label": __("September")  },
				{ "value": "10", "label": __("October")    },
				{ "value": "11", "label": __("November")   },
				{ "value": "12", "label": __("December")   }
            ],
			"reqd": 1
		},
		{
			"fieldname": "year",
			"label": __("Year"),
			"fieldtype": "Int",
			"reqd": 1
		},
		{
			"fieldname":"employee",
			"label": __("Employee"), 
			"fieldtype": "Link",
			"options": "Employee"
		},
		{
			"fieldname": "only_threshold_reached",
			"label": __("Only Threshold Reached"),
			"fieldtype": "Check"
		},
		{
			"fieldname": "only_missing_escalation",
			"label": __("Only Missing Escalation"),
			"fieldtype": "Check"
		}
	],
};
