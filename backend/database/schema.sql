-- ====================================================================
-- ProcureFlow: Operational + Intelligence Database Schema
-- PostgreSQL 16+
-- ====================================================================
-- Architecture:
--   Agency → Zone → Tender → Award → Contractor → DNA
-- ====================================================================

BEGIN;

-- ====================================================================
-- Layer 1: Core Reference Tables
-- ====================================================================

-- Agencies: procuring organizations (BWDB, RHD, LGED, PWD, etc.)
CREATE TABLE IF NOT EXISTS agencies (
    agency_code     VARCHAR(20)     PRIMARY KEY,
    agency_name     VARCHAR(300)    NOT NULL,
    ministry        VARCHAR(300)    NOT NULL,
    keyword         VARCHAR(100),
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- Zones: administrative geography (divisions → districts)
CREATE TABLE IF NOT EXISTS zones (
    zone_id         SERIAL          PRIMARY KEY,
    zone_name       VARCHAR(100)    NOT NULL UNIQUE,
    zone_type       VARCHAR(20)     NOT NULL DEFAULT 'district'
                        CHECK (zone_type IN ('division', 'district', 'upazila', 'city_corporation')),
    parent_zone_id  INTEGER         REFERENCES zones(zone_id),
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_zones_parent ON zones(parent_zone_id);
CREATE INDEX IF NOT EXISTS idx_zones_type   ON zones(zone_type);

-- ====================================================================
-- Layer 2: Core Procurement Tables
-- ====================================================================

-- Tenders: unified procurement events (identified by package_no)
-- This is the central table linking APP plans to eContracts awards.
CREATE TABLE IF NOT EXISTS tenders (
    tender_id           SERIAL          PRIMARY KEY,
    package_no          VARCHAR(300)    NOT NULL,
    title               TEXT,
    agency_code         VARCHAR(20)     NOT NULL REFERENCES agencies(agency_code),
    zone_id             INTEGER         REFERENCES zones(zone_id),
    pe_office           VARCHAR(300),
    procurement_method  VARCHAR(100),
    match_type          VARCHAR(20)     DEFAULT 'unmatched'
                        CHECK (match_type IN ('package_exact', 'synthetic', 'unmatched_app', 'unmatched_ec')),
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenders_package_no   ON tenders(package_no);
CREATE INDEX IF NOT EXISTS idx_tenders_agency       ON tenders(agency_code);
CREATE INDEX IF NOT EXISTS idx_tenders_zone         ON tenders(zone_id);
CREATE INDEX IF NOT EXISTS idx_tenders_match_type   ON tenders(match_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tenders_package_unique ON tenders(lower(package_no));

-- APP Records: planned procurement data from Annual Procurement Plan
CREATE TABLE IF NOT EXISTS app_records (
    app_id              SERIAL          PRIMARY KEY,
    tender_id           INTEGER         NOT NULL REFERENCES tenders(tender_id) ON DELETE CASCADE,
    source_tender_id    VARCHAR(50),               -- original tender_id from APP system
    title               TEXT,
    estimated_cost_bdt  NUMERIC(20,2)   DEFAULT 0,
    status              VARCHAR(50),
    published_date      DATE,
    deadline            DATE,
    financial_year      VARCHAR(20),
    app_code            VARCHAR(200),              -- APP reference code
    category            VARCHAR(100),
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE(tender_id)
);

CREATE INDEX IF NOT EXISTS idx_app_tender ON app_records(tender_id);

-- Award Records: actual contract awards from eContracts system
CREATE TABLE IF NOT EXISTS award_records (
    award_id            SERIAL          PRIMARY KEY,
    tender_id           INTEGER         NOT NULL REFERENCES tenders(tender_id) ON DELETE CASCADE,
    source_tender_id    VARCHAR(50),               -- original tender_id from eContracts
    package_no          VARCHAR(300),
    title               TEXT,
    contractor_name     VARCHAR(300),
    amount_bdt          NUMERIC(20,2)   DEFAULT 0,
    procurement_method  VARCHAR(100),
    award_date          DATE,
    detail_url          TEXT,
    is_winner           BOOLEAN         DEFAULT TRUE,
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_award_tender      ON award_records(tender_id);
CREATE INDEX IF NOT EXISTS idx_award_contractor  ON award_records(contractor_name);
CREATE INDEX IF NOT EXISTS idx_award_date        ON award_records(award_date);

-- ====================================================================
-- Layer 2b: Contractors
-- ====================================================================

CREATE TABLE IF NOT EXISTS contractors (
    contractor_id       SERIAL          PRIMARY KEY,
    contractor_name     VARCHAR(300)    NOT NULL UNIQUE,
    total_contracts     INTEGER         DEFAULT 0,
    total_amount_bdt    NUMERIC(20,2)   DEFAULT 0,
    agencies_worked     TEXT[],                      -- list of agency_codes
    districts_worked    TEXT[],
    avg_npp             NUMERIC(10,4),
    first_award_date    DATE,
    last_award_date     DATE,
    updated_at          TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contractors_name ON contractors(contractor_name);

-- ====================================================================
-- Layer 3: Procurement Lifecycle (unified view for ML/AI)
-- ====================================================================

CREATE TABLE IF NOT EXISTS procurement_lifecycle (
    lifecycle_id        SERIAL          PRIMARY KEY,
    tender_id           INTEGER         NOT NULL REFERENCES tenders(tender_id),
    package_no          VARCHAR(300)    NOT NULL,
    agency_code         VARCHAR(20)     REFERENCES agencies(agency_code),
    zone_name           VARCHAR(100),
    title               TEXT,
    estimated_cost_bdt  NUMERIC(20,2),
    award_amount_bdt    NUMERIC(20,2),
    npp_ratio           NUMERIC(10,4),
    winner              VARCHAR(300),
    award_date          DATE,
    procurement_method  VARCHAR(100),
    pe_office           VARCHAR(300),
    match_type          VARCHAR(20),
    data_source         VARCHAR(10)     DEFAULT 'matched'
                        CHECK (data_source IN ('matched', 'app_only', 'ec_only', 'synthetic')),
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_agency       ON procurement_lifecycle(agency_code);
CREATE INDEX IF NOT EXISTS idx_lifecycle_zone         ON procurement_lifecycle(zone_name);
CREATE INDEX IF NOT EXISTS idx_lifecycle_winner       ON procurement_lifecycle(winner);
CREATE INDEX IF NOT EXISTS idx_lifecycle_npp          ON procurement_lifecycle(npp_ratio);
CREATE INDEX IF NOT EXISTS idx_lifecycle_date         ON procurement_lifecycle(award_date);
CREATE INDEX IF NOT EXISTS idx_lifecycle_data_source  ON procurement_lifecycle(data_source);
CREATE INDEX IF NOT EXISTS idx_lifecycle_package      ON procurement_lifecycle(package_no);

-- ====================================================================
-- Layer 4: Intelligence / Knowledge Tables
-- ====================================================================

-- Contractor DNA: per-contractor performance profile
CREATE TABLE IF NOT EXISTS contractor_dna (
    dna_id                  SERIAL          PRIMARY KEY,
    contractor_id           INTEGER         NOT NULL REFERENCES contractors(contractor_id) ON DELETE CASCADE,
    total_contracts         INTEGER         DEFAULT 0,
    total_amount_bdt        NUMERIC(20,2)   DEFAULT 0,
    avg_award_bdt           NUMERIC(20,2)   DEFAULT 0,
    agencies_worked         INTEGER         DEFAULT 0,     -- distinct agencies
    districts_worked        INTEGER         DEFAULT 0,
    preferred_agency        VARCHAR(20),                    -- agency with most contracts
    preferred_zone          VARCHAR(100),                   -- district with most contracts
    avg_npp                 NUMERIC(10,4),
    npp_volatility          NUMERIC(10,4),                  -- stddev of NPP
    win_rate                NUMERIC(5,4)    DEFAULT 0,      -- bids won / bids submitted (future)
    avg_discount_pct        NUMERIC(10,4)   DEFAULT 0,      -- (1 - avg_npp) * 100
    specialization          TEXT,                           -- dominant work category
    first_award_date        DATE,
    last_award_date         DATE,
    contract_frequency_days INTEGER,                        -- avg days between contracts
    updated_at              TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE(contractor_id)
);

CREATE INDEX IF NOT EXISTS idx_dna_agency     ON contractor_dna(preferred_agency);
CREATE INDEX IF NOT EXISTS idx_dna_npp       ON contractor_dna(avg_npp);
CREATE INDEX IF NOT EXISTS idx_dna_win_rate  ON contractor_dna(win_rate);

-- Agency Intelligence: per-agency procurement patterns
CREATE TABLE IF NOT EXISTS agency_intelligence (
    intelligence_id         SERIAL          PRIMARY KEY,
    agency_code             VARCHAR(20)     NOT NULL REFERENCES agencies(agency_code),
    total_contracts         INTEGER         DEFAULT 0,
    total_amount_bdt        NUMERIC(20,2)   DEFAULT 0,
    avg_npp                 NUMERIC(10,4),
    npp_trend               VARCHAR(20)     DEFAULT 'stable'
                            CHECK (npp_trend IN ('rising', 'falling', 'stable', 'volatile')),
    top_contractors         JSONB,                          -- [{name, amount, count}]
    top_zones               JSONB,                          -- [{zone, amount, count}]
    preferred_method        VARCHAR(100),                   -- most used procurement method
    avg_contract_days       INTEGER,                        -- avg days from tender to award
    quarterly_spend         JSONB,                          -- [{q, year, amount}]
    updated_at              TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE(agency_code)
);

-- Zone Intelligence: per-district procurement activity
CREATE TABLE IF NOT EXISTS zone_intelligence (
    intelligence_id         SERIAL          PRIMARY KEY,
    zone_name               VARCHAR(100)    NOT NULL REFERENCES zones(zone_name),
    total_contracts         INTEGER         DEFAULT 0,
    total_amount_bdt        NUMERIC(20,2)   DEFAULT 0,
    active_agencies         INTEGER         DEFAULT 0,      -- distinct agencies operating here
    top_agencies            JSONB,                          -- [{agency, amount, count}]
    top_contractors         JSONB,
    avg_npp                 NUMERIC(10,4),
    updated_at              TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE(zone_name)
);

-- Discount Patterns: NPP patterns sliced by agency × zone × method
CREATE TABLE IF NOT EXISTS discount_patterns (
    pattern_id              SERIAL          PRIMARY KEY,
    agency_code             VARCHAR(20)     NOT NULL REFERENCES agencies(agency_code),
    zone_name               VARCHAR(100),
    procurement_method      VARCHAR(100),
    sample_size             INTEGER         DEFAULT 0,
    avg_npp                 NUMERIC(10,4),
    min_npp                 NUMERIC(10,4),
    max_npp                 NUMERIC(10,4),
    median_npp              NUMERIC(10,4),
    stddev_npp              NUMERIC(10,4),
    total_amount_bdt        NUMERIC(20,2)   DEFAULT 0,
    updated_at              TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discount_agency_method ON discount_patterns(agency_code, procurement_method);
CREATE INDEX IF NOT EXISTS idx_discount_zone          ON discount_patterns(zone_name);

-- Award Intelligence: seasonality, trends, outlier detection
CREATE TABLE IF NOT EXISTS award_intelligence (
    intelligence_id         SERIAL          PRIMARY KEY,
    agency_code             VARCHAR(20)     REFERENCES agencies(agency_code),
    fiscal_year             VARCHAR(20),
    quarter                 INTEGER         CHECK (quarter BETWEEN 1 AND 4),
    total_contracts         INTEGER         DEFAULT 0,
    total_amount_bdt        NUMERIC(20,2)   DEFAULT 0,
    avg_npp                 NUMERIC(10,4),
    avg_contract_amount     NUMERIC(20,2),
    contract_count_by_method JSONB,                        -- {method: count}
    top_contractors         JSONB,
    outlier_contracts       INTEGER         DEFAULT 0,      -- npp outside 2 stddev
    updated_at              TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_award_intel_agency_q ON award_intelligence(agency_code, fiscal_year, quarter);

-- SLT Predictions: Specific/Limited Tendering opportunity predictions
CREATE TABLE IF NOT EXISTS slt_predictions (
    prediction_id           SERIAL          PRIMARY KEY,
    agency_code             VARCHAR(20)     REFERENCES agencies(agency_code),
    zone_name               VARCHAR(100),
    predicted_packages      INTEGER,                        -- expected number of packages
    predicted_value_bdt     NUMERIC(20,2),
    confidence_score        NUMERIC(5,4),                   -- 0 to 1
    based_on_season         VARCHAR(10),                    -- which quarter this predicts
    model_version           VARCHAR(50),
    generated_at            TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_slt_agency_zone ON slt_predictions(agency_code, zone_name);

-- ====================================================================
-- Layer 5: Materialized Views for Dashboards
-- ====================================================================

-- Unified procurement view: for fast dashboard queries
CREATE MATERIALIZED VIEW IF NOT EXISTS v_procurement_summary AS
SELECT
    pl.agency_code,
    a.agency_name,
    a.ministry,
    pl.zone_name,
    pl.award_date,
    EXTRACT(YEAR FROM pl.award_date) AS award_year,
    EXTRACT(QUARTER FROM pl.award_date) AS award_quarter,
    pl.procurement_method,
    pl.winner,
    pl.estimated_cost_bdt,
    pl.award_amount_bdt,
    pl.npp_ratio,
    pl.match_type,
    pl.data_source
FROM procurement_lifecycle pl
LEFT JOIN agencies a ON pl.agency_code = a.agency_code;

CREATE INDEX IF NOT EXISTS idx_v_summary_agency   ON v_procurement_summary(agency_code);
CREATE INDEX IF NOT EXISTS idx_v_summary_zone     ON v_procurement_summary(zone_name);
CREATE INDEX IF NOT EXISTS idx_v_summary_year     ON v_procurement_summary(award_year);
CREATE INDEX IF NOT EXISTS idx_v_summary_date     ON v_procurement_summary(award_date);

-- ====================================================================
-- Layer 6: ETL Function to refresh intelligence tables
-- ====================================================================

CREATE OR REPLACE FUNCTION refresh_contractor_dna()
RETURNS TRIGGER AS $$
BEGIN
    -- Update contractor aggregate stats from award_records
    WITH contractor_stats AS (
        SELECT
            ar.contractor_name,
            COUNT(*) AS total_contracts,
            SUM(ar.amount_bdt) AS total_amount,
            AVG(pl.npp_ratio) AS avg_npp,
            STDDEV(pl.npp_ratio) AS npp_volatility,
            COUNT(DISTINCT ar.agency_code) AS agencies_worked,
            COUNT(DISTINCT ar.zone_id) AS districts_worked,
            MODE() WITHIN GROUP (ORDER BY ar.agency_code) AS preferred_agency,
            MIN(ar.award_date) AS first_award,
            MAX(ar.award_date) AS last_award
        FROM award_records ar
        LEFT JOIN procurement_lifecycle pl ON ar.tender_id = pl.tender_id
        WHERE ar.contractor_name = NEW.contractor_name
        GROUP BY ar.contractor_name
    )
    INSERT INTO contractor_dna (
        contractor_id, total_contracts, total_amount_bdt, avg_award_bdt,
        agencies_worked, districts_worked, preferred_agency, avg_npp,
        npp_volatility, avg_discount_pct, first_award_date, last_award_date
    )
    SELECT
        c.contractor_id,
        cs.total_contracts,
        cs.total_amount,
        CASE WHEN cs.total_contracts > 0 THEN cs.total_amount / cs.total_contracts ELSE 0 END,
        cs.agencies_worked,
        cs.districts_worked,
        cs.preferred_agency,
        cs.avg_npp,
        COALESCE(cs.npp_volatility, 0),
        COALESCE((1 - cs.avg_npp) * 100, 0),
        cs.first_award,
        cs.last_award
    FROM contractors c
    JOIN contractor_stats cs ON c.contractor_name = cs.contractor_name
    ON CONFLICT (contractor_id)
    DO UPDATE SET
        total_contracts      = EXCLUDED.total_contracts,
        total_amount_bdt     = EXCLUDED.total_amount_bdt,
        avg_award_bdt        = EXCLUDED.avg_award_bdt,
        agencies_worked      = EXCLUDED.agencies_worked,
        districts_worked     = EXCLUDED.districts_worked,
        preferred_agency     = EXCLUDED.preferred_agency,
        avg_npp              = EXCLUDED.avg_npp,
        npp_volatility       = EXCLUDED.npp_volatility,
        avg_discount_pct     = EXCLUDED.avg_discount_pct,
        first_award_date     = EXCLUDED.first_award_date,
        last_award_date      = EXCLUDED.last_award_date,
        updated_at           = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMIT;
