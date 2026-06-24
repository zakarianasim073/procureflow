"""Fix: restore old ContractorDNA from seed.sql, enrich with eExperience via UPDATE."""
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

    # STEP 1: DELETE all current ContractorDNA rows
    print("=" * 60)
    print("STEP 1: DELETE current ContractorDNA...")
    print("=" * 60)
    async with async_session() as db:
        await db.execute(text("DELETE FROM contractor_dna"))
        await db.commit()
    print("  Done.")

    # STEP 2: Extract clean INSERTs from seed.sql
    print()
    print("=" * 60)
    print("STEP 2: Read seed.sql, extract INSERT INTO contractor_dna...")
    print("=" * 60)
    content = Path(SEED_FILE).read_text(encoding="utf-8")

    # Remove ON CONFLICT clause so we get plain INSERTs
    content_clean = re.sub(
        r"\s+ON CONFLICT\s*\(contractor_id\)\s*DO\s+UPDATE\s+SET\s+.*?updated_at\s*=\s*NOW\(\)\s*;",
        ";",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    pattern = re.compile(
        r"INSERT INTO contractor_dna\s*\(.*?\)\s*VALUES\s*\(.*?\)\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    matches = pattern.findall(content_clean)
    print(f"  Found {len(matches)} INSERT statements")

    async with async_session() as db:
        total = 0
        errors = 0
        for i, stmt in enumerate(matches):
            try:
                await db.execute(text(stmt))
                total += 1
            except Exception:
                errors += 1
            if i % 1000 == 0 and i > 0:
                await db.commit()
                print(f"    {i}/{len(matches)} done ({errors} errors)...")
        await db.commit()
    print(f"  Restored {total} ContractorDNA rows ({errors} errors)")

    # STEP 3: Count restored
    print()
    print("=" * 60)
    print("VERIFY restoration:")
    print("=" * 60)
    async with async_session() as db:
        count = await db.scalar(select(func.count(ContractorDNA.id)))
        print(f"  ContractorDNA: {count} rows")

        # Check old columns are intact
        sample = (await db.execute(
            select(ContractorDNA).limit(3)
        )).scalars().all()
        for r in sample:
            print(f"    id={r.contractor_id[:8]}... contracts={r.total_contracts} "
                  f"amount={r.total_amount_bdt} npp={r.avg_npp} win_rate={r.win_rate} "
                  f"agencies={r.agencies_worked}")

    # STEP 4: Enrich with eExperience via UPDATE
    print()
    print("=" * 60)
    print("STEP 4: Enrich ContractorDNA with eExperience data...")
    print("=" * 60)
    async with async_session() as db:
        # Group EContractExecution by contractor name
        ee_rows = (await db.execute(select(EContractExecution))).scalars().all()
        exec_by_name = {}
        for er in ee_rows:
            if not er.contractor_name:
                continue
            n = er.contractor_name.strip().lower()
            exec_by_name.setdefault(n, []).append(er)

        contractors = (await db.execute(select(Contractor))).scalars().all()
        updated = 0
        skipped = 0

        for c in contractors:
            erows = exec_by_name.get(c.contractor_name.strip().lower(), [])
            if not erows:
                skipped += 1
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
            completion_rate = round((completed_count / max(total_exp, 1)) * 100, 2)
            on_time_rate = round((on_time_count / max(completed_count, 1)) * 100, 2) if completed_count else 0.0
            avg_delay = round(sum(delays) / len(delays), 1) if delays else 0.0

            await db.execute(
                update(ContractorDNA)
                .where(ContractorDNA.contractor_id == c.id)
                .values(
                    completion_rate=completion_rate,
                    on_time_rate=on_time_rate,
                    avg_delay_days=avg_delay,
                    total_experience_contracts=total_exp,
                    total_experience_value_bdt=round(total_exp_val, 2),
                )
            )
            updated += 1

        await db.commit()
        print(f"  Enriched {updated} rows, {skipped} skipped (no eExperience data)")

    # STEP 5: Final verification
    print()
    print("=" * 60)
    print("FINAL VERIFICATION:")
    print("=" * 60)
    async with async_session() as db:
        total = await db.scalar(select(func.count(ContractorDNA.id)))
        enriched = await db.scalar(
            select(func.count(ContractorDNA.id))
            .where(ContractorDNA.total_experience_contracts > 0)
        )
        print(f"  Total ContractorDNA: {total}")
        print(f"  Enriched with eExperience: {enriched}")

        rows = (await db.execute(
            select(ContractorDNA)
            .where(ContractorDNA.total_experience_contracts > 0)
            .order_by(ContractorDNA.total_experience_contracts.desc())
            .limit(3)
        )).scalars().all()
        for r in rows:
            print(f"    {r.contractor_id[:8]}... | exp={r.total_experience_contracts} | "
                  f"completion={r.completion_rate}% | on_time={r.on_time_rate}% | "
                  f"delay={r.avg_delay_days}d | win_rate={r.win_rate} | agencies={r.agencies_worked}")

        # NPP / analytics critical columns
        npp_ok = await db.scalar(
            select(func.count(ContractorDNA.id))
            .where(ContractorDNA.avg_npp > 0)
        )
        print(f"  Rows with avg_npp > 0: {npp_ok} (NPP dashboard depends on this)")

    await engine.dispose()
    print()
    print("Done! Old data restored + eExperience enrichment added.")


if __name__ == "__main__":
    asyncio.run(main())
