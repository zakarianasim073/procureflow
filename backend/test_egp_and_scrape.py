"""
Test eGP login, find BWDB tenders, scrape data, and send email.
Run with: python test_egp_and_scrape.py
"""
import sys, os, json, logging, time
sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("egp_test")

# ── Step 1: Login to eGP ──
from app.agents.egp_client import eGPClient

EGP_EMAIL = os.environ.get("EGP_EMAIL", "hbsrjv@gmail.com")
EGP_PASSWORD = os.environ.get("EGP_PASSWORD", "hbsrjv2017")
client = eGPClient(email=EGP_EMAIL, password=EGP_PASSWORD, timeout=30)
ok = client.login()
print(f"\n=== eGP LOGIN: {'SUCCESS' if ok else 'FAILED'} ===")
if not ok:
    print("Cannot proceed without login. Exiting.")
    sys.exit(1)

print(f"Session authenticated: {client.session.is_authenticated}")
print(f"JSESSIONID: {client.session.jsessionid[:30] if client.session.jsessionid else 'None'}...")

# ── Step 2: Search for BWDB tenders ──
print("\n=== SEARCHING FOR BWDB TENDERS ===")

# Search with keyword "BWDB"
results = client.search_tender("BWDB")
print(f"Found {len(results)} tenders for 'BWDB'")

# Search with "Water Development Board"
results2 = client.search_tender("Water Development Board")
print(f"Found {len(results2)} tenders for 'Water Development Board'")

# Search with ministry keywords
results3 = client.search_tender("water resources")
print(f"Found {len(results3)} tenders for 'water resources'")

# Combine all results
all_tenders = []
seen_ids = set()
for r in results + results2 + results3:
    tid = getattr(r, "tender_id", "") or ""
    if tid and tid not in seen_ids:
        seen_ids.add(tid)
        all_tenders.append(r)

print(f"\nTotal unique tenders found: {len(all_tenders)}")

# Filter for BWDB-related
bwdb_tenders = []
for t in all_tenders:
    entity = (getattr(t, "procuring_entity", "") or "").lower()
    title = (getattr(t, "title", "") or "").lower()
    if "bwdb" in entity or "bwdb" in title or "water development" in entity or "water development" in title:
        bwdb_tenders.append(t)

print(f"BWDB-specific tenders: {len(bwdb_tenders)}")

# ── Step 3: Try My Tender search for BWDB ──
print("\n=== MY TENDER SEARCH ===")
try:
    my_results = client.search_my_tender("BWDB")
    print(f"My Tender found {len(my_results)} BWDB tenders")
    for t in my_results:
        tid = getattr(t, "tender_id", "") or ""
        if tid and tid not in seen_ids:
            seen_ids.add(tid)
            all_tenders.append(t)
            bwdb_tenders.append(t)
except Exception as e:
    print(f"My Tender search failed: {e}")

print(f"\nTotal after My Tender: {len(all_tenders)} unique, {len(bwdb_tenders)} BWDB")

# ── Step 4: Compile tender data ──
tender_list = []
for t in all_tenders:
    item = {
        "tender_id": getattr(t, "tender_id", ""),
        "title": getattr(t, "title", ""),
        "procuring_entity": getattr(t, "procuring_entity", ""),
        "deadline": getattr(t, "deadline", ""),
        "published_date": getattr(t, "published_date", ""),
        "estimated_value_bdt": getattr(t, "estimated_value_bdt", 0),
        "category": getattr(t, "category", ""),
        "status": getattr(t, "status", ""),
    }
    tender_list.append(item)

bwdb_list = [t for t in tender_list if "bwdb" in (t["procuring_entity"] or "").lower() or "bwdb" in (t["title"] or "").lower()]

# Save to file
output = {
    "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "total_tenders": len(tender_list),
    "bwdb_tenders": len(bwdb_list),
    "all_tenders": tender_list,
    "bwdb_specific": bwdb_list,
}

output_path = os.path.join(os.path.dirname(__file__), "runtime", "data_intel", "egp_scrape_results.json")
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, default=str, ensure_ascii=False)

print(f"\nSaved {len(tender_list)} tenders to {output_path}")

# ── Step 5: Print summary ──
print(f"\n{'='*60}")
print(f"TOTAL TENDERS FOUND: {len(tender_list)}")
print(f"BWDB TENDERS: {len(bwdb_list)}")
print(f"{'='*60}")

if bwdb_list:
    print(f"\nBWDB TENDER DETAILS:")
    for t in bwdb_list:
        val = t.get("estimated_value_bdt", 0) or 0
        val_str = f"BDT {val:,.2f}" if val else "N/A"
        print(f"  {t['tender_id']:>10} | {t['title'][:60]:<60} | {val_str:>20} | {t['deadline']}")
else:
    print("\nNo BWDB tenders found in search results.")

    # Try alternative search: just get all live tenders and filter
    print("\n=== FETCHING ALL LIVE TENDERS (page 1) ===")
    all_live = client.search_tender("")
    print(f"All live tenders: {len(all_live)}")
    bwdb_from_live = []
    for t in all_live:
        entity = (getattr(t, "procuring_entity", "") or "").lower()
        title = (getattr(t, "title", "") or "").lower()
        if "bwdb" in entity or "bwdb" in title or "water development" in entity:
            bwdb_from_live.append(t)
    print(f"BWDB from all live: {len(bwdb_from_live)}")
    for t in bwdb_from_live:
        bwdb_list.append({
            "tender_id": getattr(t, "tender_id", ""),
            "title": getattr(t, "title", ""),
            "procuring_entity": getattr(t, "procuring_entity", ""),
            "deadline": getattr(t, "deadline", ""),
            "published_date": getattr(t, "published_date", ""),
            "estimated_value_bdt": getattr(t, "estimated_value_bdt", 0),
            "category": getattr(t, "category", ""),
            "status": getattr(t, "status", ""),
        })

    if bwdb_list:
        output["bwdb_specific"] = bwdb_list
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, default=str, ensure_ascii=False)
        print(f"\nBWDB TENDERS FROM LIVE SEARCH:")
        for t in bwdb_list:
            val = t.get("estimated_value_bdt", 0) or 0
            val_str = f"BDT {val:,.2f}" if val else "N/A"
            print(f"  {t['tender_id']:>10} | {t['title'][:60]:<60} | {val_str:>20} | {t['deadline']}")

# ── Step 6: Send email ──
print("\n=== SENDING EMAIL ===")
try:
    from app.services.notification_service import notification_service, TenderAlert

    sent_count = 0
    for t in bwdb_list[:20]:
        alert = TenderAlert(
            tender_id=t["tender_id"],
            title=t["title"][:200],
            procuring_entity=t["procuring_entity"],
            match_score=0.95,
            estimated_value=t.get("estimated_value_bdt", 0) or 0,
            deadline=t["deadline"],
            alert_type="new_tender",
        )
        sent = notification_service.send_tender_alert_email("z.nasim073@gmail.com", alert)
        if sent:
            sent_count += 1

    print(f"Sent {sent_count}/{len(bwdb_list)} tender alerts to z.nasim073@gmail.com")
except Exception as e:
    print(f"Email sending failed (may need SMTP config): {e}")
    # Save email data to file for manual review
    email_data = {
        "to": "z.nasim073@gmail.com",
        "subject": f"BWDB Live Tenders - {len(bwdb_list)} found",
        "tenders": bwdb_list,
    }
    email_path = os.path.join(os.path.dirname(__file__), "runtime", "data_intel", "email_pending.json")
    with open(email_path, "w", encoding="utf-8") as f:
        json.dump(email_data, f, indent=2, default=str, ensure_ascii=False)
    print(f"Email data saved to {email_path} for manual sending")

print("\n=== DONE ===")
