"""Debug the eGP /getDataForTree response format."""
import json, httpx

EGP_BASE = "https://www.eprocure.gov.bd"
client = httpx.Client(verify=False, timeout=30, follow_redirects=True)

client.get(EGP_BASE)
resp = client.post(f"{EGP_BASE}/LoginSrBean?action=checkLogin",
                   data={"emailId": "hbsrjv@gmail.com", "password": "hbsrjv2017"})
client.get(f"{EGP_BASE}/Index.jsp")
print("Logged in:", resp.status_code)

# Fetch root level
r = client.post(f"{EGP_BASE}/getDataForTree", data={"id": "0", "showPrNd": "false"})
data = r.json()
print(f"\nRoot: {len(data)} items")
if data:
    print("First item keys:", list(data[0].keys()))
    print("First item:", json.dumps(data[0], indent=2))
    for item in data[:10]:
        print(f"  id={repr(item.get('id',''))} text={repr(item.get('text',''))} state={item.get('state',{})}")
