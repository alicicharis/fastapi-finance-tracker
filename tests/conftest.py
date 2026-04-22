import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import app

DATABASE_URL_TEST = os.environ["DATABASE_URL_TEST"]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    async def _setup():
        eng = create_async_engine(DATABASE_URL_TEST, echo=False)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await eng.dispose()

    async def _teardown():
        eng = create_async_engine(DATABASE_URL_TEST, echo=False)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await eng.dispose()

    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


@pytest_asyncio.fixture
async def db():
    eng = create_async_engine(DATABASE_URL_TEST, echo=False)
    async with eng.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        yield session
        await session.close()
        await conn.rollback()
    await eng.dispose()


@pytest_asyncio.fixture
async def async_client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
