# init_db.py
import asyncio

from ibp.base import Base, engine


async def create_db_and_tables():
    """
    Creates all database tables defined in the SQLAlchemy models.
    """
    print("Attempting to create database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables created successfully (or already exist).")


if __name__ == "__main__":
    asyncio.run(create_db_and_tables())
