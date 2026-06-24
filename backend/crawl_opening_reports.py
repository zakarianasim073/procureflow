"""
Crawl Opening Reports (TOR2) from eGP Bangladesh Portal.
Extracts: bidder names, quoted amounts, package info, PE, zone/district.
"""
import requests as req, urllib3, re, json, os, time
from datetime import datetime
urllib3.disable_warnings()

BASE_URL = 'https://www.eprocure.gov.bd'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}
OUTPUT_DIR = r'D:\A1\procurementflow_final_v3\procurementflow\backend\crawl_output\OpeningReport'

DISTRICTS_BD = [
    'Bagerhat','Bandarban','Barguna','Barishal','Bhola','Bogra',
    'Brahmanbaria','Chandpur','Chattogram','Chuadanga','Comilla',
    'Cox.s Bazar','Dhaka','Dinajpur','Faridpur','Feni','Gaibandha',
    'Gazipur','Gopalganj','Habiganj','Jamalpur','Jashore','Jhalokati',
    'Jhenaidah','Joypurhat','Khagrachari','Khulna','Kishoreganj',
    'Kurigram','Kushtia','Lakshmipur','Lalmonirhat','Madaripur',
    'Magura','Manikganj','Meherpur','Moulvibazar','Munshiganj',
    'Mymensingh','Naogaon','Narail','Narayanganj','Narsingdi',
    'Natore','Nawabganj','Netrokona','Nilphamari','Noakhali',
    'Pabna','Panchagarh','Patuakhali','Pirojpur','Rajbari',
    'Rajshahi','Rangamati','Rangpur','Satkhira','Shariatpur',
    'Sherpur','Sirajganj','Sunamganj','Sylhet','Tangail','Thakurgaon',
]

def extract_zone(name):
    if not name or name == 'N/A':
        return None
    name = re.sub(r'\s+', ' ', name).strip()
    found = [(name.lower().index(d.lower()), d) for d in DISTRICTS_BD if d.lower() in name.lower()]
    if found:
        return max(found, key=lambda x: x[0])[1]
    m = re.search(r'^([A-Za-z.]+(?:\s+[A-Za-z.]+)?)\s+(?:WD|O&M|Division|Office|Zone|Circle)', name)
    return m.group(1).rstrip('.') if m else None


class OpeningReportCrawler:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.s = req.Session()
        self.s.verify = False
        self.s.headers.update(HEADERS)
        self.logged_in = False
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        os.makedirs(os.path.join(OUTPUT_DIR, 'PDF'), exist_ok=True)
        os.makedirs(os.path.join(OUTPUT_DIR, 'JSON'), exist_ok=True)

    def login(self) -> bool:
        self.s.get(BASE_URL, timeout=15)
        r = self.s.post(f'{BASE_URL}/LoginSrBean?action=checkLogin',
            data={'emailId': self.email, 'password': self.password},
            headers={'Referer': BASE_URL, 'Origin': BASE_URL},
            timeout=30, allow_redirects=False)
        if r.status_code == 302:
            self.s.get('https://www.eprocure.gov.bd/resources/common/InboxMessage.jsp',
                headers={'Referer': f'{BASE_URL}/LoginSrBean?action=checkLogin'}, timeout=15)
            self.s.get(f'{BASE_URL}/tenderer/MyTenders.jsp',
                headers={'Referer': f'{BASE_URL}/resources/common/InboxMessage.jsp'}, timeout=15)
            self.logged_in = True
            return True
        return False

    def get_archive_page(self, page: int = 1) -> str:
        r = self.s.post(f'{BASE_URL}/TenderDetailsServlet',
            data={'funName': 'MyTenders','action': 'get tenderermytenders','statusTab': 'Archive',
                'status': 'Approved','tenderId': '','refNo': '','procNature': '','procType': '',
                'procMethod': '0','pageNo': str(page),'size': '50'},
            headers={'Referer': f'{BASE_URL}/tenderer/MyTenders.jsp','X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30)
        return r.text if r.status_code == 200 else ''

    def parse_archive_html(self, html: str) -> list:
        tenders = []
        for row in re.findall(r'<tr[^>]*>.*?</tr>', html, re.DOTALL | re.I):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.I)
            if len(cells) < 5 or not cells[0].strip().isdigit():
                continue
            cell1 = cells[1]
            tid_m = re.search(r'(\d{6,})', cell1)
            if not tid_m:
                continue
            cell1_text = re.sub(r'<[^>]+>', ' ', cell1)
            cell1_text = re.sub(r'&nbsp;', ' ', cell1_text)
            cell1_text = re.sub(r'\s+', ' ', cell1_text).strip()
            parts = cell1_text.split(',', 2)
            ref_no = re.sub(r';\s*Date.*', '', parts[1].strip()) if len(parts) > 1 else ''
            status_m = re.search(r'<span[^>]*>(.*?)</span>', cell1, re.DOTALL)
            status = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', status_m.group(1))).strip() if status_m else ''
            work_name = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', cells[2])).strip()[:200] if len(cells) > 2 else ''
            pe_office = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', cells[3])).strip() if len(cells) > 3 else ''
            tenderers_count = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', cells[4])).strip() if len(cells) > 4 else ''
            tenders.append({
                'tender_id': tid_m.group(1), 'ref_no': ref_no, 'status': status,
                'work_name': work_name, 'pe_office': pe_office,
                'zone': extract_zone(pe_office), 'tenderers_count': tenderers_count,
            })
        return tenders

    def get_all_archived_tenders(self) -> list:
        all_tenders = []
        page = 1
        while True:
            html = self.get_archive_page(page)
            if not html:
                break
            tenders = self.parse_archive_html(html)
            if not tenders:
                break
            all_tenders.extend(tenders)
            print(f'  Page {page}: {len(tenders)} tenders')
            if len(tenders) < 50:
                break
            page += 1
            time.sleep(0.5)
        return all_tenders

    def extract_tor2_metadata(self, html: str, tender_id: str) -> dict:
        meta = {'tender_id': tender_id}
        label_map = {
            'Tender/Proposal ID': 'tender_id', 'Invitation Reference No': 'ref_no',
            'Closing Date and Time': 'closing_date', 'Opening Date and Time': 'opening_date',
            'Procuring Entity': 'procuring_entity', 'Tender/Proposal Status': 'tender_status',
            'Ministry Name': 'ministry_name', 'Organization/Agency Name': 'agency_name',
            'Tender Package No': 'package_no', 'Lot No': 'lot_no',
        }
        for tbl in re.findall(r'<table[^>]*>.*?</table>', html, re.DOTALL | re.I):
            for row in re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL | re.I):
                cells = re.findall(r'<td[^>]*>\s*(.*?)\s*</td>', row, re.DOTALL | re.I)
                for ci, cell in enumerate(cells):
                    label = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', cell)).strip()
                    for pat, key in label_map.items():
                        if label.startswith(pat) and key not in meta and ci + 1 < len(cells):
                            val = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', cells[ci + 1])).strip()
                            if val:
                                meta[key] = val

        if meta.get('procuring_entity'):
            meta['zone'] = extract_zone(meta['procuring_entity'])

        bidders = []
        price_bidders = []
        for tbl in re.findall(r'<table[^>]*>.*?</table>', html, re.DOTALL | re.I):
            if 'Name of Tenderer' not in tbl:
                continue
            is_price = 'Quoted Amount' in tbl
            for row in re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.DOTALL | re.I):
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL | re.I)
                if len(cells) < 4:
                    continue
                s_no = re.sub(r'<[^>]+>', '', cells[0]).strip()
                if not s_no.isdigit():
                    continue
                name = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', cells[1])).strip()
                if not name:
                    continue
                if is_price:
                    price_bidders.append({
                        'serial': int(s_no), 'name': name,
                        'quoted_amount': re.sub(r'<[^>]+>', '', cells[2]).strip(),
                        'discount_pct': re.sub(r'<[^>]+>', '', cells[3]).strip() if len(cells) > 3 else '',
                        'discount_amount': re.sub(r'<[^>]+>', '', cells[4]).strip() if len(cells) > 4 else '',
                        'net_quoted': re.sub(r'<[^>]+>', '', cells[5]).strip() if len(cells) > 5 else '',
                    })
                else:
                    bidders.append({'serial': int(s_no), 'name': name})
        if bidders:
            meta['bidder_count'] = len(bidders)
            meta['bidders'] = bidders
        if price_bidders:
            meta['price_bid_count'] = len(price_bidders)
            meta['price_bids'] = price_bidders
        if not bidders and not price_bidders:
            meta['bidder_count'] = 0
        return meta

    def download_report(self, tender_id: str, archive_info: dict = None) -> dict:
        result = {'tender_id': tender_id, 'lot_id': '0'}
        pdf_path = os.path.join(OUTPUT_DIR, 'PDF', f'{tender_id}.pdf')
        json_path = os.path.join(OUTPUT_DIR, 'JSON', f'{tender_id}.json')

        try:
            r = self.s.get(f'{BASE_URL}/report/TOR2.jsp',
                params={'isT': 'y', 'isPDF': 'false', 'tenderid': tender_id, 'lotId': '0'},
                headers={'Referer': f'{BASE_URL}/tenderer/MyTenders.jsp'}, timeout=30)
            if r.status_code != 200 or len(r.text) < 100:
                result['error'] = f'TOR2.jsp returned {r.status_code} ({len(r.text)}B)'
                return result
            result['html_size'] = len(r.text)

            meta = self.extract_tor2_metadata(r.text, tender_id)
            # Merge archive info
            if archive_info:
                if not meta.get('procuring_entity') and archive_info.get('pe_office'):
                    meta['procuring_entity'] = archive_info['pe_office']
                if not meta.get('zone') and archive_info.get('zone'):
                    meta['zone'] = archive_info['zone']
            result['metadata'] = meta

            r2 = self.s.get(f'{BASE_URL}/TorRptServlet',
                params={'tenderId': tender_id, 'lotId': '0', 'action': 'TOR2'},
                headers={
                    'Referer': f'{BASE_URL}/report/TOR2.jsp?isT=y&isPDF=false&tenderid={tender_id}&lotId=0',
                    'Accept': 'application/pdf,image/webp,*/*',
                }, timeout=120)
            if r2.status_code == 200 and r2.content[:4] == b'%PDF':
                with open(pdf_path, 'wb') as f:
                    f.write(r2.content)
                result['pdf_path'] = pdf_path
                result['pdf_size'] = len(r2.content)
            else:
                result['pdf_error'] = f'TorRptServlet: {r2.status_code} {len(r2.content)}B'

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2, default=str)
            result['json_path'] = json_path

        except Exception as e:
            result['error'] = str(e)[:200]
        return result

    def ensure_session(self) -> bool:
        return True if (self.logged_in and self.s.cookies.get('JSESSIONID')) else self.login()

    def crawl(self, max_tenders: int = None):
        print('=== eGP Opening Report Crawler ===')
        print(f'Account: {self.email}')
        if not self.ensure_session():
            return

        all_tenders = self.get_all_archived_tenders()
        print(f'\nTotal archived tenders: {len(all_tenders)}')

        manifest = {
            'crawled_at': datetime.now().isoformat(), 'email': self.email,
            'total_tenders': len(all_tenders), 'tenders': all_tenders,
        }
        with open(os.path.join(OUTPUT_DIR, 'archive_manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=1, default=str)

        already_done = set()
        for fname in os.listdir(os.path.join(OUTPUT_DIR, 'PDF')):
            if fname.endswith('.pdf'):
                already_done.add(fname.replace('.pdf', ''))
        to_process = [t for t in all_tenders if t['tender_id'] not in already_done]
        if max_tenders:
            to_process = to_process[:max_tenders]
        already_skipped = len(all_tenders) - len(to_process)
        if already_skipped:
            print(f'Skipping {already_skipped} already downloaded')

        results = []
        for i, tender in enumerate(to_process):
            if i % 50 == 0 and i > 0:
                self.ensure_session()
            tid = tender['tender_id']
            print(f'\n[{i+1}/{len(to_process)}] Tender {tid} ({tender.get("ref_no","?")[:40]})...',
                  end=' ', flush=True)
            tor = self.download_report(tid, archive_info=tender)
            if tor.get('error'):
                if 'Session' in tor.get('error', '') and self.login():
                    tor = self.download_report(tid, archive_info=tender)
                if tor.get('error'):
                    print(f'ERR: {tor["error"]}', flush=True)
                    continue
            if tor.get('pdf_path'):
                meta = tor.get('metadata', {})
                print(f'PDF={tor["pdf_size"]}B bidders={meta.get("bidder_count","?")} '
                      f'zone={meta.get("zone","?")}', flush=True)
            if tor.get('pdf_error'):
                print(f'PDF-ERR: {tor["pdf_error"]}', flush=True)
            tor['tender_info'] = tender
            results.append(tor)
            time.sleep(0.5)

        report = {
            'crawled_at': datetime.now().isoformat(), 'total_tenders': len(all_tenders),
            'processed': len(to_process) + already_skipped,
            'new_downloads': len([r for r in results if r.get('pdf_path')]),
            'skipped': already_skipped, 'failed': len([r for r in results if r.get('error')]),
            'results': results,
        }
        with open(os.path.join(OUTPUT_DIR, 'crawl_results.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=1, default=str)
        print(f'\n\n=== Done ===')
        print(f'New: {report["new_downloads"]}, Skipped: {report["skipped"]}, Failed: {report["failed"]}')
        return report


if __name__ == '__main__':
    import sys
    email = sys.argv[1] if len(sys.argv) > 1 else 'info@handbl.com'
    password = sys.argv[2] if len(sys.argv) > 2 else 'infohandbl2018'
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
    OpeningReportCrawler(email, password).crawl(max_tenders=limit)
