# Unified Schema — package_no as Primary Join Key

- 2026-06-14 — [Decision: All three data sources (APP, Award, eExperience) MUST have `package_no` as the primary key for cross-matching. Plus `work_name` (title/description) required in all three. Schema finalized:
  - APP: package_no, work_name, agency, location, district, estimated_cost_bdt, title, status, financial_year, app_code, category, published_date, deadline
  - Award: package_no, work_name, amount_bdt, contractor_name, procurement_method, award_date, agency_code, district, pe_office
  - eExperience: package_no, work_name, contract_value_bdt, completed_value_bdt, contractor_name, completion_status, completed_on_time, actual_completion_date, planned_completion_date, contract_start_date, contract_end_date, progress_pct, district, agency_code, pe_name](dc://w/procurementflow/c/eexperience-crawl/m/all)
