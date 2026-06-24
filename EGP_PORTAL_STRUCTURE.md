# e-GP Portal Structure (www.eprocure.gov.bd)
## Complete Site Map for Procurement Flow Agents

### 1. PUBLIC SECTIONS (No Login Required)

```
┌─────────────────────────────────────────────────────────────────────┐
│  HOMEPAGE (/)                                                       │
│  ├── Advance Search  → /resources/common/AllTenders.jsp?h=t        │
│  ├── eTenders        → /resources/common/StdTenderSearch.jsp?h=t   │
│  ├── APP             → /resources/common/SearchAPP.jsp             │
│  ├── eContracts/NOA  → /resources/common/SearchNOA.jsp             │
│  ├── eExperience     → /resources/common/SearcheCMS.jsp            │
│  ├── Offline Tenders → /resources/common/SearchTenderOffline.jsp   │
│  ├── Offline Awards  → /resources/common/SearchAwardedContractOffline.jsp
│  └── Debarred        → /resources/common/DebarmentRpt.jsp          │
└─────────────────────────────────────────────────────────────────────┘
```

### 2. PUBLIC AJAX ENDPOINTS

| Endpoint | Method | Purpose | Key Params |
|----------|--------|---------|------------|
| `/TenderDetailsServlet` | POST | Tender data (all tabs) | `funName=AllTenders, viewType=Live|Archive|AllTenders|Cancel, pageNo, size, h=t` |
| `/SearchNoaServlet` | POST | NOA award data | `keyword, pageNo, size` |
| `/SearchAPPServlet` | POST | Annual Procurement Plan | `action=advSearch, pageNo, size, keyWord, bTypeId, office` |
| `/ComboServlet` | POST | Department/Office dropdowns | `departmentId, funName=officeCombo` |
| `/SearchServlet` | POST | General search | `keyWord, pageNo, size, action` |
| `/PDFServlet` | POST | PDF generation | Various |

### 3. AllTenders.jsp (Advance Search) — Tab Structure

The main tender search page has multiple SEARCH TABS:
```
┌─────────────┬──────────────┬────────────┬──────────────┐
│  eTenders   │ APP          │ eContracts │ eExperience  │
│  (Tab 1)    │ (Tab 2)      │ (Tab 3)    │ (Tab 4)      │
├─────────────┴──────────────┴────────────┴──────────────┤
│  URL: /resources/common/AllTenders.jsp?h=t              │
│  AJAX: POST /TenderDetailsServlet                        │
└─────────────────────────────────────────────────────────┘
```

Each eTenders tab has SUB-TABS (viewType):
- **Live** (`viewType=Live`) — Currently active tenders
- **Archive** (`viewType=Archive`) — Recently closed
- **AllTenders** (`viewType=AllTenders`) — All (rejected/other)
- **Cancel** (`viewType=Cancel`) — Cancelled tenders

#### Search Filters (AllTenders.jsp):
```
departmentId, office, procNature (Goods/Works/Services),
procType (NCT/ICT), procMethod (RFQ/OTM/DPP, etc.),
tenderId, refNo, pubDtFrm/pubDtTo, closeDtFrm/closeDtTo,
cpvCategory, isFrame (Yes/No), pageNo, size
```

#### NOA Search Filters (AdvSearchNOA.jsp):
```
Search by keyword, department, office, date range, tender ID
```

#### APP Search Filters (AdvAPPSearch.jsp / SearchAPPServlet):
```
bTypeId, office, keyWord, pageNo, size, action=advSearch
Also: txtdepartment, txtdepartmentid, cmbDistrict, financialYear
```

### 4. AUTHENTICATED SECTIONS (Login Required)

```
┌──────────────────────────────────────────────────────────────────────┐
│  POST /LoginSrBean?action=checkLogin                                │
│  Body: emailId, password                                             │
│  Redirect: → /UpdateUpazila.jsp or /UpdateMobileNid.jsp (bypass)    │
│  Bypass: GET /Index.jsp  → confirms login                           │
│  Session cookies: JSESSIONID, CPTU-COOKIE                            │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  My Dashboard  → /resources/common/InboxMessage.jsp                 │
│    - User inbox/messages                                            │
│    - Quick links to My Tender, etc.                                  │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  My Tender  → /tenderer/MyTenders.jsp (redirects to dashboard)      │
│    Shows tenders user has purchased schedules for.                   │
│    Subtabs: Live/Pending, Archive/Approved                           │
└──────────────────────────────────────────────────────────────────────┘
```

### 5. TENDER DETAILS & DOCUMENTS

#### View Tender Details:
```
URL:     /resources/common/ViewTender.jsp?id=TENDER_ID&h=t
Method:  GET or POST
Access:  PUBLIC (no login needed to view)
Content:
  • Ministry/Organization Info
  • Procurement Method & Budget
  • Package Info (Code, Name, Package No, Category)
  • Eligibility Criteria
  • Goods/Services Description
  • Lot Details (Lot No, Location, Start/End Dates)
  • Inviting Officer Info
  • Documents Link → /tenderer/LotPckDocs.jsp?tenderId=X
  • Save As PDF    → /GeneratePdf?reqURL=...&id=X
```

#### Tender Documents (requires tenderer role + schedule purchase):
```
URL:     /tenderer/LotPckDocs.jsp?tenderId=TENDER_ID
Access:  REQUIRES AUTH (tenderer who purchased schedule)
Documents typically available:
  • NIT (Notice Inviting Tender)
  • TDC (Tender Data Card) — Key tender terms
  • GCC (General Conditions of Contract)
  • PCC (Particular Conditions of Contract)
  • BOQ (Bill of Quantities) — Rate schedule
  • Drawings / Designs
  • Schedules & Formats
  • Corrigendum / Addendum
```

### 6. CONTRACT SIGNING SECTION

After tender award, accessible from tender dashboard:
```
Actions available:
  • Contract Agreement Forms
  • Performance Security / Bank Guarantee
  • Advance Payment Documents
  • Contract Signing Details
  • Mapped Documents & Information
```

### 7. OTHER ENDPOINTS DISCOVERED

| Endpoint | Purpose |
|----------|---------|
| `/WatchListServlet` | Add/Remove tenders from watchlist |
| `/PDFServlet` | Generate PDF of tender notice |
| `/GeneratePdf?reqURL=...&id=...` | Generate PDF from any page |
| `/ComboServlet` | Dynamic dropdown data (department→office) |
| `/officer/Notice.jsp?tenderid=X` | Officer's notice page |
| `/resources/common/ViewTender.jsp?id=X&h=t` | Tender details (main) |
| `/DownloadDocumentServlet?param=...` | Download tender documents |

### 8. DATA FLOW FOR AGENTS

```
Agent 1: TenderRadarAgent
  ├── search_tender(keyword)      → POST /TenderDetailsServlet (public)
  ├── search_all_tenders()         → All 4 viewType tabs (public)
  └── get_tender_by_id(id)        → ViewTender.jsp (public)

Agent 2: TenderAcquisitionAgent
  ├── search_my_tender(keyword)   → Requires login (purchased schedules)
  └── download_document(id, type) → Requires tenderer role

Agent 14: AwardIntelligenceAgent
  ├── search_noa()                 → POST /SearchNoaServlet (public)
  ├── search_offline_awards()      → POST (public)
  └── collect_award_intelligence() → NOA + optional auth sources

Agent 22: EGPRateFillAgent
  ├── get_tender_by_id(id)        → ViewTender.jsp
  ├── download_document(id, 'BOQ')→ Download tender BOQ
  └── Rate data from BOQ docs
```

### 9. CREDENTIALS

- **Demo Account**: hbsrjv@gmail.com / hbsrjv2017
- **eCMS/eExperience**: Requires real login (demo account has limited access)
- **Document Download**: Requires tenderer role + purchased schedule
- **My Tender**: Shows only user's purchased tenders

### 10. RATE LIMITING NOTES

- Portal limits requests from single IP
- Recommended delays: 2-5 seconds between requests
- Max retries: 3 per endpoint
- Session timeout: ~20 minutes of inactivity
