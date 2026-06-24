"""Explore the eGP department tree via /getDataForTree to map agencies to IDs."""
import json, re, httpx, urllib.parse

EGP_BASE = "https://www.eprocure.gov.bd"
client = httpx.Client(verify=False, timeout=30, follow_redirects=True)

# Login
client.get(EGP_BASE)
resp = client.post(f"{EGP_BASE}/LoginSrBean?action=checkLogin",
                   data={"emailId": "hbsrjv@gmail.com", "password": "hbsrjv2017"})
client.get(f"{EGP_BASE}/Index.jsp")
print("Logged in:", resp.status_code)

def get_tree(parent_id="0", show_prnd="false"):
    """Fetch children of a tree node."""
    r = client.post(f"{EGP_BASE}/getDataForTree",
                    data={"id": parent_id, "showPrNd": show_prnd})
    try:
        return r.json()
    except:
        print(f"  RAW for id={parent_id}: {r.text[:200]}")
        return []

# Fetch root level
print("\n=== ROOT NODES (Ministries) ===")
root = get_tree("0")
for item in root:
    node_id = item.get("id", "")
    text = item.get("text", "")
    print(f"  ID: {node_id} | {text}")

print("\n=== EXPANDING KEY MINISTRIES ===")

# Define target keywords
TARGETS = [
    "Local Government", "Road Transport", "Bridge", "Water Resources",
    "Housing", "Public Works", "Power", "Health", "Education",
    "Agriculture", "Fisheries", "Shipping", "Railway", "Defence",
    "Science", "Environment", "Disaster", "Civil Aviation", "Commerce",
    "Industries", "Planning", "Finance"
]

# For each root node, expand 2 levels deep to find target departments
def expand_node(node_id, text, depth=0, max_depth=3, path=""):
    """Recursively expand tree nodes looking for targets."""
    full_path = f"{path} > {text}" if path else text
    indent = "  " * (depth + 1)
    
    # Check if this matches a target at leaf level
    children = get_tree(f"deptid_{node_id}" if not node_id.startswith("deptid_") and node_id != "0" else node_id)
    
    if not children:
        # Leaf node - check if it's a department
        if any(kw in text.lower() for kw in ["lged", "pwd", "rhd", "bwdb", "badc", "lgd"]):
            print(f"{indent}★ LEAF: deptid={node_id} | {full_path}")
        return children
    
    matches = False
    for child in children:
        cid = child.get("id", "")
        ctext = child.get("text", "")
        # Check if this or any ancestor path matches targets
        for kw in TARGETS:
            if kw.lower() in ctext.lower() or kw.lower() in text.lower():
                matches = True
                break
        if matches:
            break
    
    if matches or depth < 1:
        for child in children:
            cid = child.get("id", "")
            ctext = child.get("text", "")
            expand_node(cid, ctext, depth + 1, max_depth, full_path)
    
    return children

# Expand root nodes
for item in root:
    node_id = item.get("id", "")
    text = item.get("text", "")
    expand_node(node_id, text, 0, 3)

print("\n=== DONE ===")
