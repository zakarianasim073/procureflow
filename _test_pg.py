import asyncio, asyncpg, os

async def test():
    try:
        conn = await asyncpg.connect(
            user=os.environ.get("PG_USER", "procurementflow"),
            password=os.environ.get("PG_PASSWORD", "procurementflow"),
            host=os.environ.get("PG_HOST", "localhost"),
            port=int(os.environ.get("PG_PORT", "5432")),
            database=os.environ.get("PG_DATABASE", "procurementflow")
        )
        print('Connected OK')
        row = await conn.fetchrow('SELECT count(*) as cnt FROM award_records_v2')
        cnt = row['cnt']
        print(f'award_records_v2 count: {cnt}')
        row2 = await conn.fetchrow('SELECT count(*) as cnt FROM agencies')
        print(f'agencies count: {row2["cnt"]}')
        await conn.close()
    except Exception as e:
        print(f'Error: {e}')

asyncio.run(test())
