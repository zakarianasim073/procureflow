"""Merge: run seed.sql UPSERTs on top of current ContractorDNA, then enrich with eExperience."""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, select, update, func
from app.models.intelligence import ContractorDNA, EContractExecution, Contractor

DATABASE_URL = "postgresql+asyncpg://procurementflow:procurementflow@localhost:5432/procurementflow"
SEED_FILE = Path(__file__).parent / "database" / "seed.sql"


async def main():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 60)
    print("STEP 1: Read seed.sql, extract INSERT INTO contractor_dna (with ON CONFLICT)...")
    print("=" * 60)
    content = Path(SEED_FILE).read_text(encoding="utf-8")

    pattern = re.compile(
        r"INSERT INTO contractor_dna\s*\(.*?\)\s*VALUES\s*\(.*?\)\s*ON CONFLICT.*?;",
        re.IGNORECASE | re.DOTALL,
    )
    matches = pattern.findall(content)
    print(f"  Found {len(matches)} UPSERT statements")

    async with async_session() as db:
        before = await db.scalar(select(func.count(ContractorDNA.id)))
        print(f"  ContractorDNA before: {before}")

        # Run in batches of 1000
        batch_size = 1000
        total = 0
        errors = 0
        for i in range(0, len(matches), batch_size):
            batch = matches[i : i + batch_size]
            for stmt in batch:
                try:
                    await db.execute(text(stmt))
                    total += 1
                except Exception:
                    errors += 1
            await db.commit()
            pct = min(i + batch_size, len(matches))
            print(f"    {pct}/{len(matches)} ({errors} errors)...")

        after = await db.scalar(select(func.count(ContractorDNA.id)))
    print(f"  Done. {total} processed, {errors} errors. Rows: {before} -> {after}")

    # STEP 2: Enrich with eExperience
    print()
    print("=" * 60)
    print("STEP 2: Enrich ContractorDNA with eExperience data via UPDATE...")
    print("=" * 60)
    async with async_session() as db:
        ee_rows = (await db.execute(select(EContractExecution))).scalars().all()
        exec_by_name = {}
        for er in ee_rows:
            if not er.contractor_name:
                continue
            exec_by_name.setdefault(er.contractor_name.strip().lower(), []).append(er)

        contractors = (await db.execute(select(Contractor))).scalars().all()
        updated = 0
        for c in contractors:
            erows = exec_by_name.get(c.contractor_name.strip().lower(), [])
            if not erows:
                continue
            total_exp = len(erows)
            total_exp_val = sum(float(r.contract_value_bdt or 0) for r in erows)
            completed_count = sum(
                1 for r in erows
                if r.actual_completion_date
                or (r.completion_status and "complete" in r.completion_status.lower())
                or (r.status and "complete" in r.status.lower())
            )
            on_time_count = sum(1 for r in erows if r.completed_on_time is True)
            delays = [r.delay_days for r in erows if r.delay_days and r.delay_days > 0]
            await db.execute(
                update(ContractorDNA)
                .where(ContractorDNA.contractor_id == c.id)
                .values(
                    completion_rate=round((completed_count / max(total_exp, 1)) * 100, 2),
                    on_time_rate=round((on_time_count / max(completed_count, 1)) * 100, 2) if completed_count else 0.0,
                    avg_delay_days=round(sum(delays) / len(delays), 1) if delays else 0.0,
                    total_experience_contracts=total_exp,
                    total_experience_value_bdt=round(total_exp_val, 2),
                )
            )
            updated += 1
        await db.commit()
    print(f"  Enriched {updated} ContractorDNA rows")

    # STEP 3: Verify
    print()
    print("=" * 60)
    print("VERIFICATION:")
    print("=" * 60)
    async with async_session() as db:
        total = await db.scalar(select(func.count(ContractorDNA.id)))
        enriched = await db.scalar(
            select(func.count(ContractorDNA.id)).where(ContractorDNA.total_experience_contracts > 0)
        )
        npp_ok = await db.scalar(
            select(func.count(ContractorDNA.id)).where(ContractorDNA.avg_npp > 0)
        )
        win_rate_ok = await db.scalar(
            select(func.count(ContractorDNA.id)).where(ContractorDNA.win_rate > 0)
        )
        print(f"  Total: {total}")
        print(f"  With eExperience enrichment: {enriched}")
        print(f"  With avg_npp > 0: {npp_ok}")
        print(f"  With win_rate > 0: {win_rate_ok}")

        sample = (await db.execute(
            select(ContractorDNA)
            .where(ContractorDNA.total_experience_contracts > 0)
            .order_by(ContractorDNA.total_experience_contracts.desc())
            .limit(3)
        )).scalars().all()
        for r in sample:
            print(f"    {r.contractor_id[:8]}... | contracts={r.total_contracts} | "
                  f"npp={r.avg_npp} | win={r.win_rate} | agencies={r.agencies_worked} | "
                  f"exp_contracts={r.total_experience_contracts} | "
                  f"completion={r.completion_rate}% | on_time={r.on_time_rate}%")

    await engine.dispose()
    print()
    print("Done! All old data preserved + eExperience enrichment added.")


if __name__ == "__main__":
    asyncio.run(main())
