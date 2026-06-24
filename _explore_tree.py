"""Properly explore eGP department tree to find all department IDs."""
import json, httpx

EGP_BASE = "https://www.eprocure.gov.bd"
client = httpx.Client(verify=False, timeout=30, follow_redirects=True)

client.get(EGP_BASE)
resp = client.post(f"{EGP_BASE}/LoginSrBean?action=checkLogin",
                   data={"emailId": "hbsrjv@gmail.com", "password": "hbsrjv2017"})
client.get(f"{EGP_BASE}/Index.jsp")
print("Logged in:", resp.status_code)

seen_ids = set()
leaf_depts = {}  # name -> id mapping

def get_children(node_id):
    """Fetch children of a tree node."""
    r = client.post(f"{EGP_BASE}/getDataForTree",
                    data={"id": node_id, "showPrNd": "false"})
    try:
        return r.json()
    except:
        return []

def traverse(node_id, depth=0, path=""):
    """Recursively traverse the tree."""
    if node_id in seen_ids:
        return
    seen_ids.add(node_id)
    
    children = get_children(node_id)
    for child in children:
        attr = child.get("attr", {})
        cid = attr.get("id", "")
        cname = attr.get("dname", "")
        dtype = attr.get("dtype", "")
        cdata = child.get("data", "")
        display = cdata or cname
        
        full_path = f"{path} > {display}" if path else display
        
        # Leaf department nodes
        if dtype == "Department" or (not children and depth > 0):
            # Only store if it has a valid deptid
            if cid and cid.startswith("deptid_"):
                num_id = cid.replace("deptid_", "")
                leaf_depts[full_path] = num_id
        
        # Print all nodes
        indent = "  " * depth
        has_children = child.get("state") == "closed"
        icon = "📂" if has_children else "📄"
        print(f"{indent}{icon} [{dtype}] {display} ({cid})")
        
        if has_children and cid:
            traverse(cid, depth + 1, full_path)

# Start from root
print("=== FULL TREE ===\n")
root = get_children("0")
for item in root:
    attr = item.get("attr", {})
    cid = attr.get("id", "")
    cname = attr.get("dname", "")
    dtype = attr.get("dtype", "")
    cdata = item.get("data", "")
    display = cdata or cname
    print(f"[{dtype}] {display} ({cid})")
    if item.get("state") == "closed" and cid:
        traverse(cid, 1, display)

print(f"\n\n=== TOTAL LEAF DEPARTMENTS: {len(leaf_depts)} ===\n")

# Find specific targets
targets = ["LGED", "PWD", "RHD", "Roads", "BADC", "Health Engineering",
           "BWDB", "Water", "Power", "Education", "Agriculture",
           "Local Government", "Housing", "Public Works", "Bridge",
           "Railway", "Shipping"]

for name, dept_id in sorted(leaf_depts.items()):
    for t in targets:
        if t.lower() in name.lower():
            print(f"  {dept_id} | {name}")
            break

# Save
out = {"departments": leaf_depts}
with open("backend/runtime/knowledge/app/dept_tree.json", "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"\nSaved to backend/runtime/knowledge/app/dept_tree.json")
