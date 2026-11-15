from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import DatasetAcquisitionError, TerraTwinError, domain_exception_handler
from app.main import global_exception_handler, validation_exception_handler


async def test_internal_error_never_exposes_exception():
    app = FastAPI()
    app.add_exception_handler(Exception, global_exception_handler)

    @app.get("/fail")
    async def fail():
        raise RuntimeError("password=secret /private/file")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.get("/fail")
    assert response.status_code == 500
    assert "secret" not in response.text
    assert response.json()["error"]["details"] is None


async def test_validation_error_does_not_echo_input():
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @app.get("/validate")
    def validate(count: int):
        return count

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/validate?count=secret")
    assert response.status_code == 422
    assert "secret" not in response.text
    assert response.json()["error"]["details"]["fields"][0]["location"] == ["query", "count"]


async def test_dataset_acquisition_failure_is_structured_gateway_error():
    app = FastAPI()
    app.add_exception_handler(TerraTwinError, domain_exception_handler)

    @app.get("/acquire")
    async def acquire():
        raise DatasetAcquisitionError("Remote dataset download failed")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/acquire")
    assert response.status_code == 502
    assert response.json()["error"]["type"] == "DatasetAcquisitionError"
