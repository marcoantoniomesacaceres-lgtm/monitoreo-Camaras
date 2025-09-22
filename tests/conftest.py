import pytest
from httpx import AsyncClient
from main import app

@pytest.fixture
async def client():
    """
    Fixture global para usar AsyncClient con la app de FastAPI.
    Permite hacer peticiones HTTP a los endpoints en todos los tests.
    """
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac 