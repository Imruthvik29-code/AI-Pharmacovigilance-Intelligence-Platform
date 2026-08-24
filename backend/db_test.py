import os
import asyncio
import asyncpg
from dotenv import load_dotenv

load_dotenv("backend/.env")

async def main():
    url = os.environ["DATABASE_URL"]
    url = url.replace("postgresql+asyncpg://", "postgresql://", 1)

    conn = await asyncpg.connect(url)

    version = await conn.fetchval(
        "SELECT version_num FROM alembic_version"
    )

    table_exists = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'rxnorm_concept_relations'
        )
        """
    )

    print("Alembic version:", version)
    print("rxnorm_concept_relations exists:", table_exists)

    await conn.close()

asyncio.run(main())