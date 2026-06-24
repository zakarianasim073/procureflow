"""Test BOQ compare with simple zone string vs dict zone"""
import httpx, json

api = "http://localhost:8000/api"

# Test 1: Simple zone string
print("=== Test 1: zone='B' ===")
resp = httpx.post(
    f"{api}/boq/compare",
    data={
        "boq_file_id": "57c20c63",
        "sor_agency": "BWDB",
        "zone": "B",
        "tender_info": json.dumps({"tender_id":"1290886","title":"test"}),
    },
    timeout=30,
)
print(f"Status: {resp.status_code}")
print(resp.text[:500])

# Test 2: JSON dict zone
print("\n=== Test 2: zone as JSON dict ===")
resp = httpx.post(
    f"{api}/boq/compare",
    data={
        "boq_file_id": "57c20c63",
        "sor_agency": "BWDB",
        "zone": '{"BWDB":"B","PWD":"B","LGED":"B"}',
        "tender_info": json.dumps({"tender_id":"1290886","title":"test"}),
    },
    timeout=30,
)
print(f"Status: {resp.status_code}")
print(resp.text[:500])
