#!/usr/bin/env python
import frappe
from frappe.model.workflow import apply_workflow

def test_escalation():
    """Test workflow rejection and escalation trigger"""
    
    # Get warning in Pending Approval
    warnings = frappe.get_all(
        "HR Attendance Warning", 
        filters={"workflow_state": "Pending Approval"}, 
        limit=1
    )
    
    if not warnings:
        print("No warnings in Pending Approval state")
        return
    
    warning_name = warnings[0].name
    print(f"Testing warning: {warning_name}\n")
    
    doc = frappe.get_doc("HR Attendance Warning", warning_name)
    print(f"Before rejection:")
    print(f"  workflow_state: {doc.workflow_state}")
    print(f"  approval_decision: {doc.approval_decision}\n")
    
    try:
        # Apply Reject action
        print("Applying 'Reject' workflow action...\n")
        apply_workflow(doc, "Reject")
        
        print(f"After rejection:")
        print(f"  workflow_state: {doc.workflow_state}")
        print(f"  approval_decision: {doc.approval_decision}\n")
        
        # Check if escalation was created
        escalations = frappe.get_all(
            "HR Attendance Escalation Action",
            filters={"employee": doc.employee}
        )
        print(f"Escalations for {doc.employee}: {len(escalations)}")
        for esc in escalations:
            print(f"  - {esc.name}: Month={esc.get('month')}, Count={esc.get('rejected_warning_count')}")
            
    except Exception as e:
        print(f"Error applying workflow: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_escalation()
