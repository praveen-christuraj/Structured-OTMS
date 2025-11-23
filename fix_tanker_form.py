#!/usr/bin/env python3
"""
Script to remove st.form() wrapper from tanker_transactions.py
to enable live updates like tank_transactions.py
"""

import re

# Read the file
with open(r'd:\Project OTMS-Rebuild\app_pages\tanker_transactions.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and process the form section
output_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    
    # Remove the form start line
    if 'with st.form("tanker_transaction_form"' in line and i > 570 and i < 590:
        # Skip this line entirely
        i += 1
        continue
    
    # Replace form_submit_button with regular button
    if 'st.form_submit_button' in line and i > 730 and i < 750:
        # Replace form_submit_button with button
        line = line.replace('st.form_submit_button', 'st.button')
        # Add type="primary" and key
        line = line.replace('disabled=not can_submit)', 'type="primary", disabled=not can_submit, key="tanker_tx_submit")')
        output_lines.append(line)
        i += 1
        continue
    
    # De-indent lines that were inside the form (lines 579-735 approximately)
    if i > 578 and i < 740:
        # If line starts with more than 4 spaces of indentation (was inside form), reduce by 4
        if line.startswith('        '):  # 8+ spaces
            # Check if it's a try/except or with block that should stay indented
            stripped = line.lstrip()
            if stripped.startswith(('try:', 'except', 'with get_session')):
                output_lines.append(line)
            else:
                # Remove 4 spaces
                output_lines.append(line[4:])
        else:
            output_lines.append(line)
    else:
        output_lines.append(line)
    
    i += 1

# Write back
with open(r'd:\Project OTMS-Rebuild\app_pages\tanker_transactions.py', 'w', encoding='utf-8') as f:
    f.writelines(output_lines)

print("Successfully removed st.form() wrapper and de-indented content")
print("The form now allows live updates like tank_transactions.py")
