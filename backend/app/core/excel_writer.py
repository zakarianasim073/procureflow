"""BOQ Excel Report Writer - Generates 5-sheet analysis workbook"""

import xlsxwriter
from pathlib import Path
from datetime import datetime


def write_boq_analysis(
    filepath: str,
    tender_info: dict,
    comparison_rows: list,
    summary_rows: list,
    flagged_rows: list,
    financial_rows: list,
):
    """Generate complete 5-sheet BOQ analysis Excel matching the sample format."""
    workbook = xlsxwriter.Workbook(str(filepath))

    # ── Formats ──────────────────────────────────────────────────────────────
    header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#1e40af", "font_color": "#ffffff",
        "border": 1, "align": "center", "text_wrap": True, "valign": "vcenter"
    })
    title_fmt = workbook.add_format({
        "bold": True, "font_size": 14, "font_color": "#1e40af"
    })
    subtitle_fmt = workbook.add_format({
        "bold": True, "font_size": 11, "font_color": "#374151"
    })
    label_fmt = workbook.add_format({
        "bold": True, "border": 1, "bg_color": "#f3f4f6", "valign": "vcenter"
    })
    value_fmt = workbook.add_format({
        "border": 1, "valign": "vcenter"
    })
    num_fmt = workbook.add_format({
        "border": 1, "num_format": "#,##0.00", "valign": "vcenter"
    })
    pct_fmt = workbook.add_format({
        "border": 1, "num_format": "0.00%", "valign": "vcenter"
    })
    total_label_fmt = workbook.add_format({
        "bold": True, "border": 1, "bg_color": "#dbeafe", "valign": "vcenter"
    })
    total_num_fmt = workbook.add_format({
        "bold": True, "border": 1, "bg_color": "#dbeafe",
        "num_format": "#,##0.00", "valign": "vcenter"
    })

    # Status colors
    ok_fmt = workbook.add_format({"border": 1, "bg_color": "#dcfce7", "valign": "vcenter"})
    ok_num = workbook.add_format({"border": 1, "bg_color": "#dcfce7", "num_format": "#,##0.00"})
    warn_fmt = workbook.add_format({"border": 1, "bg_color": "#fef9c3", "valign": "vcenter"})
    warn_num = workbook.add_format({"border": 1, "bg_color": "#fef9c3", "num_format": "#,##0.00"})
    err_fmt = workbook.add_format({"border": 1, "bg_color": "#fecaca", "valign": "vcenter"})
    err_num = workbook.add_format({"border": 1, "bg_color": "#fecaca", "num_format": "#,##0.00"})
    below_fmt = workbook.add_format({"border": 1, "bg_color": "#dbeafe", "font_color": "#1d4ed8", "valign": "vcenter"})
    below_num = workbook.add_format({"border": 1, "bg_color": "#dbeafe", "font_color": "#1d4ed8", "num_format": "#,##0.00"})
    miss_fmt = workbook.add_format({"border": 1, "bg_color": "#e0e7ff", "valign": "vcenter"})
    sor_not_found_fmt = workbook.add_format({
        "border": 1, "bg_color": "#fecaca", "font_color": "#b91c1c",
        "bold": True, "font_size": 10, "valign": "vcenter"
    })
    section_fmt = workbook.add_format({
        "bold": True, "border": 1, "bg_color": "#f0f9ff",
        "font_color": "#0369a1", "valign": "vcenter"
    })

    def get_fmts(flag):
        m = {"AT SOR": (ok_fmt, ok_num), "VARIANCE": (warn_fmt, warn_num),
             "MISMATCH": (err_fmt, err_num), "BELOW SOR": (below_fmt, below_num),
             "ABOVE SOR": (err_fmt, err_num), "SOR NOT FOUND": (sor_not_found_fmt, sor_not_found_fmt)}
        return m.get(flag, (miss_fmt, miss_fmt))

    def emoji(flag):
        return {"AT SOR": "✅", "VARIANCE": "⚠", "MISMATCH": "🔴",
                "BELOW SOR": "🔵", "ABOVE SOR": "🔴"}.get(flag, "❓")

    # ═══════════════════════════════════════════════════════════════════════════
    # SHEET 1: Tender Summary
    # ═══════════════════════════════════════════════════════════════════════════
    ws1 = workbook.add_worksheet("Tender Summary")
    ws1.set_column(0, 0, 3)
    ws1.set_column(1, 4, 30)
    ws1.set_column(5, 8, 18)

    row = 0
    ws1.merge_range(row, 0, row, 8, "", workbook.add_format())
    row += 1
    ws1.merge_range(row, 1, row, 8,
        f"🏗  BOQ vs SOR RATE ANALYSIS — TENDER ID: {tender_info.get('tender_id', 'N/A')}", title_fmt)
    row += 1
    ws1.merge_range(row, 1, row, 8, tender_info.get("title", ""), subtitle_fmt)
    row += 2

    estimated_cost_app = tender_info.get("estimated_cost_app")
    info_fields = [
        ("Procuring Entity", tender_info.get("entity")),
        ("Location", tender_info.get("location")),
        ("Agency / SOR", tender_info.get("sor_agency")),
        ("Zone", tender_info.get("zone")),
        ("Invitation Ref.", tender_info.get("invitation_ref")),
        ("Tender ID", tender_info.get("tender_id")),
        ("Estimated Cost (APP)", f"Tk. {estimated_cost_app:,.2f}" if estimated_cost_app else ""),
        ("Tender Security", tender_info.get("tender_security")),
        ("Closing Date", tender_info.get("closing_date")),
        ("Work Period", tender_info.get("work_period")),
        ("Report Generated", datetime.now().strftime("%d-%b-%Y %H:%M")),
    ]
    for i, (lbl, val) in enumerate(info_fields):
        ws1.write(row + i, 2, lbl, label_fmt)
        ws1.merge_range(row + i, 3, row + i, 4, val or "", value_fmt)

    row += len(info_fields) + 1
    ws1.write(row, 2, "Total SOR Amount (BDT)", label_fmt)
    ws1.merge_range(row, 5, row, 6, tender_info.get("total_sor", 0), num_fmt)
    row += 1
    ws1.write(row, 2, "Total Quoted Amount (BDT)", label_fmt)
    ws1.merge_range(row, 5, row, 6, tender_info.get("total_quoted", 0), num_fmt)
    row += 1
    ws1.write(row, 2, "Saving vs SOR (BDT)", label_fmt)
    ws1.merge_range(row, 5, row, 6, tender_info.get("saving", 0), num_fmt)
    row += 1
    ws1.write(row, 2, "Discount (%)", label_fmt)
    ws1.merge_range(row, 5, row, 6, tender_info.get("discount_pct", 0), pct_fmt)
    row += 1
    if estimated_cost_app:
        total_sor = tender_info.get("total_sor", 0)
        deviation = total_sor - estimated_cost_app
        dev_pct = deviation / estimated_cost_app if estimated_cost_app else 0
        ws1.write(row, 2, "APP Estimated Cost (BDT)", label_fmt)
        ws1.merge_range(row, 5, row, 6, estimated_cost_app, num_fmt)
        row += 1
        ws1.write(row, 2, "Deviation (SOR - APP)", label_fmt)
        ws1.merge_range(row, 5, row, 6, deviation, num_fmt)
        row += 1
        ws1.write(row, 2, "Deviation (%)", label_fmt)
        ws1.merge_range(row, 5, row, 6, dev_pct, pct_fmt)
    row += 2

    # Qualification section
    ws1.merge_range(row, 1, row, 8, "QUALIFICATION REQUIREMENTS (TDS)", subtitle_fmt)
    row += 1
    quals = tender_info.get("qualifications", [])
    for q in quals:
        ws1.write(row, 2, q.get("criterion", ""), label_fmt)
        ws1.merge_range(row, 3, row, 8, q.get("detail", ""), value_fmt)
        row += 1

    # ═══════════════════════════════════════════════════════════════════════════
    # SHEET 2: BOQ Rate Comparison
    # ═══════════════════════════════════════════════════════════════════════════
    ws2 = workbook.add_worksheet("BOQ Rate Comparison")
    ws2.merge_range(0, 0, 0, 14,
        f"BOQ vs SOR RATE COMPARISON — Tender {tender_info.get('tender_id', '')} — {tender_info.get('title', '')}",
        title_fmt)
    ws2.merge_range(1, 0, 1, 14,
        "  LEGEND:   ✅ AT SOR (±1%)    ⚠ VARIANCE (1–10%)    🔵 BELOW SOR (>10% discount)    🔴 ABOVE SOR (>10% premium)   |   Agencies: BWDB = Water Dev Board  |  PWD = Public Works  |  LGED = Local Gov Eng",
        workbook.add_format({"font_size": 9, "font_color": "#6b7280"}))

    headers2 = ["#", "Item\nCode", "Agency", "Work\nType", "Description of Item",
                 "Unit", "Quantity", "SOR\nRate (BDT)", "SOR\nAmount (BDT)",
                 "Quoted\nRate (BDT)", "Quoted\nAmount (BDT)", "Rate\nDiff (BDT)",
                 "Variance\n(%)", "Status", "Remarks"]
    ws2.set_column(0, 0, 5)
    ws2.set_column(1, 1, 14)
    ws2.set_column(2, 3, 10)
    ws2.set_column(4, 4, 55)
    ws2.set_column(5, 5, 7)
    ws2.set_column(6, 12, 13)
    ws2.set_column(13, 13, 16)
    ws2.set_column(14, 14, 16)

    for ci, h in enumerate(headers2):
        ws2.write(2, ci, h, header_fmt)
    ws2.freeze_panes(3, 0)

    current_section = ""
    ri = 3
    for item in comparison_rows:
        section = item.get("section", "")
        if section and section != current_section:
            ws2.merge_range(ri, 0, ri, 14, f"▶  {section}", section_fmt)
            ri += 1
            current_section = section

        flag = item.get("flag", "OK")
        tf, nf = get_fmts(flag)

        ws2.write(ri, 0, item.get("item_no", ""), tf)
        ws2.write(ri, 1, item.get("code", ""), tf)
        ws2.write(ri, 2, item.get("agency", ""), tf)
        ws2.write(ri, 3, item.get("work_type", ""), tf)
        ws2.write(ri, 4, item.get("desc", ""), tf)
        ws2.write(ri, 5, item.get("unit", ""), tf)

        qty = item.get("qty") or 0
        ws2.write_number(ri, 6, float(qty), nf)
        sor_rate = item.get("sor_rate")
        quoted_rate = item.get("rate")
        sor_amt = float(qty) * float(sor_rate) if sor_rate else 0
        quoted_amt = float(qty) * float(quoted_rate) if quoted_rate else 0

        if sor_rate is not None:
            ws2.write_number(ri, 7, float(sor_rate), nf)
            ws2.write_number(ri, 8, sor_amt, nf)
        else:
            ws2.write(ri, 7, "N/A", tf)
            ws2.write(ri, 8, "N/A", tf)

        if quoted_rate is not None:
            ws2.write_number(ri, 9, float(quoted_rate), nf)
            ws2.write_number(ri, 10, quoted_amt, nf)
        else:
            ws2.write(ri, 9, "N/A", tf)
            ws2.write(ri, 10, "N/A", tf)

        diff = item.get("diff")
        pct = item.get("pct_diff")
        ws2.write_number(ri, 11, float(diff) if diff is not None else 0, nf)
        ws2.write_number(ri, 12, float(pct) if pct is not None else 0, nf)
        ws2.write(ri, 13, flag, tf)

        remarks = item.get("remarks", "")
        if remarks == "SOR NOT FOUND":
            ws2.write(ri, 14, remarks, sor_not_found_fmt)
        else:
            ws2.write(ri, 14, remarks, tf)
        ri += 1

    # ═══════════════════════════════════════════════════════════════════════════
    # SHEET 3: Work Type Summary
    # ═══════════════════════════════════════════════════════════════════════════
    ws3 = workbook.add_worksheet("Work Type Summary")
    ws3.merge_range(0, 0, 0, 8,
        f"WORK TYPE — COST SUMMARY & BREAKDOWN — Tender {tender_info.get('tender_id', '')}", title_fmt)

    s_headers = ["Work Type", "Items", "SOR Amount (BDT)", "Quoted Amount (BDT)",
                  "Saving (BDT)", "Discount (%)", "% of Quoted Total"]
    for ci, h in enumerate(s_headers):
        ws3.write(1, ci, h, header_fmt)

    ws3.set_column(0, 0, 22)
    ws3.set_column(1, 6, 20)

    for ri, r in enumerate(summary_rows, start=2):
        ws3.write(ri, 0, r.get("work_type", ""), value_fmt)
        ws3.write(ri, 1, r.get("items", 0), num_fmt)
        ws3.write_number(ri, 2, float(r.get("sor_amount", 0)), num_fmt)
        ws3.write_number(ri, 3, float(r.get("quoted_amount", 0)), num_fmt)
        ws3.write_number(ri, 4, float(r.get("saving", 0)), num_fmt)
        ws3.write_number(ri, 5, float(r.get("discount_pct", 0)), pct_fmt)
        ws3.write_number(ri, 6, float(r.get("pct_of_total", 0)), pct_fmt)

    total_row = len(summary_rows) + 2
    ws3.write(total_row, 0, "TOTAL", total_label_fmt)
    ws3.write(total_row, 1, sum(r.get("items", 0) for r in summary_rows), total_num_fmt)
    ws3.write_number(total_row, 2, tender_info.get("total_sor", 0), total_num_fmt)
    ws3.write_number(total_row, 3, tender_info.get("total_quoted", 0), total_num_fmt)
    ws3.write_number(total_row, 4, tender_info.get("saving", 0), total_num_fmt)
    ws3.write_number(total_row, 5, tender_info.get("discount_pct", 0), workbook.add_format({
        "bold": True, "border": 1, "bg_color": "#dbeafe", "num_format": "0.00%"
    }))
    ws3.write_number(total_row, 6, 1.0, total_num_fmt)

    # ═══════════════════════════════════════════════════════════════════════════
    # SHEET 4: Rate Detail & Flags
    # ═══════════════════════════════════════════════════════════════════════════
    ws4 = workbook.add_worksheet("Rate Detail & Flags")
    ws4.merge_range(0, 0, 0, 10,
        "RATE DETAIL — FLAGGED ITEMS FOR REVIEW / NEGOTIATION", title_fmt)

    f_headers = ["#", "Code", "Agency", "Description", "Unit", "Qty",
                  "SOR Rate", "Quoted Rate", "Saving/Unit", "Total Saving", "Status"]
    ws4.set_column(0, 0, 5)
    ws4.set_column(1, 1, 14)
    ws4.set_column(2, 2, 10)
    ws4.set_column(3, 3, 55)
    ws4.set_column(4, 4, 7)
    ws4.set_column(5, 9, 14)
    ws4.set_column(10, 10, 16)

    for ci, h in enumerate(f_headers):
        ws4.write(1, ci, h, header_fmt)

    for ri, r in enumerate(flagged_rows, start=2):
        flag = r.get("flag", "OK")
        tf, nf = get_fmts(flag)

        ws4.write(ri, 0, r.get("item_no", ""), tf)
        ws4.write(ri, 1, r.get("code", ""), tf)
        ws4.write(ri, 2, r.get("agency", ""), tf)
        ws4.write(ri, 3, r.get("desc", ""), tf)
        ws4.write(ri, 4, r.get("unit", ""), tf)
        ws4.write_number(ri, 5, float(r.get("qty", 0)), nf)
        sor_rate = r.get("sor_rate", 0) or 0
        quoted_rate = r.get("rate", 0) or 0
        ws4.write_number(ri, 6, float(sor_rate), nf)
        ws4.write_number(ri, 7, float(quoted_rate), nf)
        saving_per = float(sor_rate) - float(quoted_rate)
        ws4.write_number(ri, 8, saving_per, nf)
        ws4.write_number(ri, 9, saving_per * float(r.get("qty", 0)), nf)
        ws4.write(ri, 10, flag, tf)

    # ═══════════════════════════════════════════════════════════════════════════
    # SHEET 5: Financial Check
    # ═══════════════════════════════════════════════════════════════════════════
    ws5 = workbook.add_worksheet("Financial Check")
    ws5.merge_range(0, 0, 0, 6,
        f"FINANCIAL QUALIFICATION CHECKLIST — {tender_info.get('entity', '')}", title_fmt)

    fin_headers = ["", "Criterion", "Required", "Our Figure", "Remarks", "Status"]
    ws5.set_column(0, 0, 3)
    ws5.set_column(1, 4, 30)
    ws5.set_column(5, 5, 14)

    for ci, h in enumerate(fin_headers):
        ws5.write(1, ci, h, header_fmt)

    for ri, r in enumerate(financial_rows, start=2):
        status = r.get("status", "")
        sf = workbook.add_format({"border": 1, "valign": "vcenter",
            "bg_color": "#dcfce7" if "OK" in str(status) else "#fef9c3"})
        ws5.write(ri, 0, "", value_fmt)
        ws5.write(ri, 1, r.get("criterion", ""), label_fmt)
        ws5.write(ri, 2, r.get("required", ""), value_fmt)
        ws5.write(ri, 3, r.get("our_figure", ""), value_fmt)
        ws5.write(ri, 4, r.get("remarks", ""), value_fmt)
        ws5.write(ri, 5, status, sf)

    workbook.close()
