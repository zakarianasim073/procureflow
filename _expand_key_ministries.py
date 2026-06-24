"""Expand key ministries to find department IDs for LGED, PWD, RHD, etc."""
import json, httpx

EGP_BASE = "https://www.eprocure.gov.bd"
client = httpx.Client(verify=False, timeout=30, follow_redirects=True)

client.get(EGP_BASE)
resp = client.post(f"{EGP_BASE}/LoginSrBean?action=checkLogin",
                   data={"emailId": "hbsrjv@gmail.com", "password": "hbsrjv2017"})
client.get(f"{EGP_BASE}/Index.jsp")
print("Logged in:", resp.status_code)

def clean_id(node_id):
    """Strip deptid_ prefix to get numeric ID."""
    return node_id.replace("deptid_", "") if node_id else "0"

def get_children(node_id):
    numeric = clean_id(node_id)
    r = client.post(f"{EGP_BASE}/getDataForTree",
                    data={"id": numeric, "showPrNd": "false"})
    try:
        return r.json()
    except:
        print(f"  NON-JSON for {node_id}: {r.text[:300]}")
        return []

def show_node(item, depth=0, node_id=""):
    attr = item.get("attr", {})
    cid = attr.get("id", node_id)
    cname = attr.get("dname", "")
    dtype = attr.get("dtype", "")
    cdata = item.get("data", "")
    display = cdata or cname
    state = item.get("state", "open")
    indent = "  " * depth
    icon = "[+]" if state == "closed" else "[_]"
    print(f"{indent}{icon} [{dtype}] {display} (id={cid})")
    return cid, display, state

def expand_ministry(min_name, min_id, max_depth=5):
    numeric = clean_id(min_id)
    print(f"\n{'='*60}")
    print(f"EXPANDING: {min_name} (id={min_id}, numeric={numeric})")
    print(f"{'='*60}")
    
    level1 = get_children(min_id)
    for l1 in level1:
        l1_id, l1_name, l1_state = show_node(l1, 1, min_id)
        if l1_state == "closed" and max_depth >= 2:
            level2 = get_children(l1_id)
            for l2 in level2:
                l2_id, l2_name, l2_state = show_node(l2, 2, l1_id)
                if l2_state == "closed" and max_depth >= 3:
                    level3 = get_children(l2_id)
                    for l3 in level3:
                        l3_id, l3_name, l3_state = show_node(l3, 3, l2_id)
                        if l3_state == "closed" and max_depth >= 4:
                            level4 = get_children(l3_id)
                            for l4 in level4:
                                l4_id, l4_name, l4_state = show_node(l4, 4, l3_id)
                                if l4_state == "closed" and max_depth >= 5:
                                    level5 = get_children(l4_id)
                                    for l5 in level5:
                                        show_node(l5, 5, l4_id)

# Key ministries
ministries = [
    ("Ministry of Local Government, Rural Development and Co-operatives", "deptid_3"),
    ("Ministry of Road Transport and Bridges", "deptid_8"),
    ("Ministry of Housing and Public Works", "deptid_20"),
    ("Ministry of Water Resources", "deptid_6"),
    ("Ministry of Agriculture", "deptid_38"),
    ("Ministry of Health and Family Welfare", "deptid_58"),
    ("Ministry of Education", "deptid_40"),
    ("Ministry of Energy, Power and Mineral Resources", "deptid_11"),
    ("Ministry of Railways", "deptid_162"),
    ("Ministry of Shipping", "deptid_97"),
    ("Ministry of Primary and Mass Education", "deptid_30"),
    ("Ministry of Industries", "deptid_111"),
    ("Ministry of Disaster Management & Relief", "deptid_145"),
    ("Ministry of Fisheries & Livestock", "deptid_157"),
    ("Ministry of Science and Technology", "deptid_176"),
    ("Ministry of Defence", "deptid_166"),
    ("Ministry of Civil Aviation & Tourism", "deptid_142"),
    ("Ministry of Planning", "deptid_14"),
    ("Ministry of Finance", "deptid_45"),
]

for name, mid in ministries:
    expand_ministry(name, mid, max_depth=3)
