import asyncio
import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

load_dotenv("backend/.env", override=True)

async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"])

    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT
                column_name,
                data_type,
                character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'alembic_version'
              AND column_name = 'version_num';
        """))

        row = result.fetchone()
        print(row)

    await engine.dispose()

asyncio.run(main())