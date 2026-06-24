"""
Scrape ALL live tenders from eGP, filter for BWDB, save + send email.
"""
import sys, os, json, logging, time, re
sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bwdb_scraper")

# Login
from app.agents.egp_client import eGPClient

EGP_EMAIL = os.environ.get("EGP_EMAIL", "hbsrjv@gmail.com")
EGP_PASSWORD = os.environ.get("EGP_PASSWORD", "hbsrjv2017")
client = eGPClient(email=EGP_EMAIL, password=EGP_PASSWORD, timeout=30)
if not client.login():
    print("eGP login FAILED")
    sys.exit(1)
print("eGP login OK")

# Collect ALL live tenders (multiple pages)
print("\n=== Collecting ALL live tenders ===")
all_live = []
for page in range(1, 11):
    try:
        results = client.search_tender("", page=page, size=100)
        if results:
            all_live.extend(results)
            print(f"  Page {page}: {len(results)} tenders (total: {len(all_live)})")
        else:
            print(f"  Page {page}: empty — stopping")
            break
    except Exception as e:
        print(f"  Page {page} error: {e}")
        break

print(f"\nTotal live tenders collected: {len(all_live)}")

# Build tender list
tender_list = []
for t in all_live:
    entity = (getattr(t, "procuring_entity", "") or "").strip()
    title = (getattr(t, "title", "") or "").strip()
    tid = getattr(t, "tender_id", "") or ""
    
    item = {
        "tender_id": tid,
        "title": title,
        "procuring_entity": entity,
        "deadline": getattr(t, "deadline", ""),
        "published_date": getattr(t, "published_date", ""),
        "estimated_value_bdt": getattr(t, "estimated_value_bdt", 0),
        "category": getattr(t, "category", ""),
        "status": getattr(t, "status", ""),
    }
    tender_list.append(item)

# Filter for BWDB / Water Development Board
bwdb_entities = ["bwdb", "water development board", "bangladesh water", "পানি উন্নয়ন বোর্ড"]
bwdb_list = []
non_bwdb_list = []

for t in tender_list:
    entity_lower = (t["procuring_entity"] or "").lower()
    title_lower = (t["title"] or "").lower()
    is_bwdb = any(kw in entity_lower or kw in title_lower for kw in bwdb_entities)
    if is_bwdb:
        bwdb_list.append(t)
    else:
        non_bwdb_list.append(t)

print(f"\nBWDB tenders: {len(bwdb_list)}")
print(f"Other tenders: {len(non_bwdb_list)}")

# Print BWDB tenders
if bwdb_list:
    print("\n" + "="*80)
    print(f"{'ID':>10} | {'Title':<50} | {'Value (BDT)':>15} | {'Deadline'}")
    print("="*80)
    for t in bwdb_list:
        val = t.get("estimated_value_bdt", 0) or 0
        val_str = f"{val:,.0f}" if val else "N/A"
        print(f"  {t['tender_id']:>8} | {t['title'][:48]:<48} | {val_str:>15} | {t['deadline']}")
else:
    print("\nNo BWDB-specific tenders found.")
    # Show the entity list to help identify BWDB
    entities = {}
    for t in tender_list:
        e = t["procuring_entity"] or "Unknown"
        entities[e] = entities.get(e, 0) + 1
    sorted_entities = sorted(entities.items(), key=lambda x: -x[1])
    print("\nTop procuring entities (for reference):")
    for e, c in sorted_entities[:20]:
        print(f"  {c:>4}x | {e}")

# Save to file
runtime_dir = os.path.join(os.path.dirname(__file__), "runtime", "data_intel")
os.makedirs(runtime_dir, exist_ok=True)

output = {
    "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "total_tenders": len(tender_list),
    "bwdb_count": len(bwdb_list),
    "bwdb_tenders": bwdb_list,
    "all_tenders": tender_list if len(tender_list) <= 100 else f"{len(tender_list)} tenders (see full file)",
}

path = os.path.join(runtime_dir, "bwdb_live_tenders.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, default=str, ensure_ascii=False)
print(f"\nSaved to {path}")

# Send email (if SMTP configured)
print("\n=== Sending email to z.nasim073@gmail.com ===")
try:
    body_parts = []
    bwdb_preview = bwdb_list[:20]
    if bwdb_preview:
        body_parts.append(f"Found {len(bwdb_list)} BWDB live tenders on eGP:\n")
        for t in bwdb_preview:
            val = t.get("estimated_value_bdt", 0) or 0
            body_parts.append(f"  ID: {t['tender_id']}")
            body_parts.append(f"  Title: {t['title'][:100]}")
            body_parts.append(f"  Entity: {t['procuring_entity']}")
            body_parts.append(f"  Value: BDT {val:,.0f}" if val else "  Value: N/A")
            body_parts.append(f"  Deadline: {t['deadline']}")
            body_parts.append("")
    else:
        body_parts.append("No BWDB tenders found in current live search.")
        body_parts.append(f"\nTotal {len(tender_list)} live tenders checked.")
        body_parts.append("\nTop entities found:")
        entities = {}
        for t in tender_list[:50]:
            e = t["procuring_entity"] or "Unknown"
            entities[e] = entities.get(e, 0) + 1
        for e, c in sorted(entities.items(), key=lambda x: -x[1])[:15]:
            body_parts.append(f"  {c}x {e}")
    
    body = "\n".join(body_parts)
    
    # Save to a file that can be read
    email_path = os.path.join(runtime_dir, "email_to_z_nasim.json")
    email_data = {
        "to": "z.nasim073@gmail.com",
        "subject": f"BWDB Live Tenders Report - {len(bwdb_list)} found ({len(tender_list)} total)",
        "body": body,
        "bwdb_count": len(bwdb_list),
        "total_count": len(tender_list),
    }
    with open(email_path, "w", encoding="utf-8") as f:
        json.dump(email_data, f, indent=2, default=str, ensure_ascii=False)
    print(f"Email data saved to {email_path}")
    
    # Try sending via SMTP
    try:
        from app.services.notification_service import notification_service, TenderAlert
        sent = 0
        for t in bwdb_list[:10]:
            alert = TenderAlert(
                tender_id=t["tender_id"],
                title=t["title"][:200],
                procuring_entity=t["procuring_entity"],
                match_score=0.95,
                estimated_value=t.get("estimated_value_bdt", 0) or 0,
                deadline=t["deadline"],
                alert_type="new_tender",
            )
            if notification_service.send_tender_alert_email("z.nasim073@gmail.com", alert):
                sent += 1
        print(f"Email alerts sent via SMTP: {sent}/{min(len(bwdb_list), 10)}")
    except Exception as smtp_err:
        print(f"SMTP send failed (config SMTP_EMAIL/SMTP_PASSWORD in .env): {smtp_err}")
except Exception as e:
    print(f"Email step error: {e}")

print("\n=== COMPLETE ===")
