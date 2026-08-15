#!/usr/bin/env python
"""Fix the raw string syntax error in core/tests.py line 2309."""
import sys

filepath = "core/tests.py"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Line 2309 (0-indexed 2308) has a raw string with escaped double quotes
# that fails to terminate: r"name=\"..."
# Replace with single-quoted raw string so double quotes don't need escaping.
old_pattern = 'r"name=\\"csrfmiddlewaretoken\\" value=\\"([^\\"]+)\\""'
new_pattern = "r'name=\"csrfmiddlewaretoken\" value=\"([^\"]+)\"'"

fixed_any = False
for i, line in enumerate(lines):
    if old_pattern in line:
        lines[i] = line.replace(old_pattern, new_pattern)
        fixed_any = True
        print(f"Fixed line {i+1}")

if not fixed_any:
    print("Pattern not found. Dumping lines around 2308-2312:")
    for j in range(2305, min(2315, len(lines))):
        print(f"  {j+1}: {repr(lines[j])}")
else:
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("File written successfully.")
