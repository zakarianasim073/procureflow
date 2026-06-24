"""Test the new parse logic."""
import re, sys
sys.stdout.reconfigure(encoding='utf-8')

line = "INSERT INTO agencies (agency_code, agency_name, ministry, keyword) VALUES ('BWDB', 'Bangladesh Water Development Board', 'Ministry of Water Resources', 'BWDB') ON CONFLICT DO NOTHING;"
line = re.sub(r" ON CONFLICT DO NOTHING", "", line)

m = re.match(r"INSERT INTO (\w+)\s*\(([^)]+)\)\s*", line)
if m:
    print("Table:", m.group(1))
    print("Cols:", m.group(2))
    rest = line[m.end():].strip()
    print("Rest:", repr(rest[:200]))
    m2 = re.search(r"VALUES\s*", rest)
    if m2:
        vals_text = rest[m2.end():].strip()
        print("Vals text:", repr(vals_text[:200]))
