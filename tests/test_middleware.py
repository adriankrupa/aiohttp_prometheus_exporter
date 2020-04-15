import typing

import prometheus_client
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient
from aiohttp.web_response import json_response
from prometheus_client import parser

from aiohttp_prometheus_exporter.handler import metrics
from aiohttp_prometheus_exporter.middleware import prometheus_middleware_factory


@pytest.fixture
def app():
    """ create a test app with various endpoints for the test scenarios """
    app = web.Application()
    routes = web.RouteTableDef()

    registry = prometheus_client.CollectorRegistry()

    app.middlewares.append(prometheus_middleware_factory(registry=registry))
    app.router.add_get("/metrics", metrics(registry=registry))

    @routes.get("/200")
    async def response_200(_):
        return json_response({"message": "Hello World"})

    @routes.get("/exception")
    async def response_exception(_):
        raise ValueError("Error")

    @routes.get("/path/{value}")
    async def response_detail(request):
        return json_response({"message": f"Hello {request.match_info['value']}"})

    app.router.add_routes(routes)

    #
    # @app.route("/500")
    # async def error(request):
    #     raise HTTPException(status_code=500, detail="this is a test error")
    #
    # @app.route("/unhandled")
    # async def unhandled(request):
    #     test_dict = {"yup": 123}
    #     return JSONResponse({"message": test_dict["value_error"]})

    yield app


class TestMiddleware:
    @pytest.fixture()
    async def client(self, aiohttp_client, app) -> TestClient:
        return await aiohttp_client(app)

    @pytest.mark.parametrize(
        "path,path_template,server_response",
        [
            ("/200", "/200", 200),
            ("/path/123", "/path/{value}", 200),
            ("/random_path", "__not_matched__", 404),
        ],
    )
    async def test_ok(
        self, client: TestClient, path: str, path_template: str, server_response: int
    ):
        resp = await client.get(path)
        assert resp.status == server_response

        metrics_response = await client.get("/metrics")
        assert metrics_response.status == 200

        metrics_text = await metrics_response.text()

        families = text_string_to_metric_families_map(metrics_text)

        assert_entry_exist(
            families,
            "aiohttp_requests",
            {
                "method": "GET",
                "path_template": path_template,
                "remote": "127.0.0.1",
                "scheme": "http",
            },
            1.0,
        )

        assert_entry_exist(
            families,
            "aiohttp_responses",
            {
                "method": "GET",
                "path_template": path_template,
                "remote": "127.0.0.1",
                "scheme": "http",
                "status_code": f"{server_response}",
            },
            1.0,
        )

        assert_entry_exist(
            families,
            "aiohttp_requests_in_progress",
            {
                "method": "GET",
                "path_template": path_template,
                "remote": "127.0.0.1",
                "scheme": "http",
            },
            0.0,
        )

        assert_entry_exist(
            families,
            "aiohttp_requests_in_progress",
            {
                "method": "GET",
                "path_template": path_template,
                "remote": "127.0.0.1",
                "scheme": "http",
            },
            0.0,
        )

        assert_entry_exist(
            families,
            "aiohttp_request_duration_seconds",
            {
                "method": "GET",
                "path_template": path_template,
                "remote": "127.0.0.1",
                "scheme": "http",
            },
        )

    @pytest.mark.parametrize(
        "path,path_template,server_response", [("/exception", "/exception", 500)]
    )
    async def test_exception(
        self, client: TestClient, path: str, path_template: str, server_response: int
    ):
        resp = await client.get("/exception")
        assert resp.status == server_response

        metrics_response = await client.get("/metrics")
        assert metrics_response.status == 200

        metrics_text = await metrics_response.text()

        families = text_string_to_metric_families_map(metrics_text)

        assert_entry_exist(
            families,
            "aiohttp_requests",
            {
                "method": "GET",
                "path_template": "/exception",
                "remote": "127.0.0.1",
                "scheme": "http",
            },
            1.0,
        )

        assert_entry_exist(
            families,
            "aiohttp_requests_in_progress",
            {
                "method": "GET",
                "path_template": "/exception",
                "remote": "127.0.0.1",
                "scheme": "http",
            },
            0.0,
        )

        assert_entry_exist(
            families,
            "aiohttp_exceptions",
            {
                "method": "GET",
                "path_template": "/exception",
                "remote": "127.0.0.1",
                "scheme": "http",
                "exception_type": "ValueError",
            },
            1.0,
        )


def assert_entry_exist(
    families: typing.Mapping[str, prometheus_client.Metric],
    metric_name: str,
    labels: typing.Mapping[str, str],
    value: float = None,
):
    metric = families[metric_name]

    samples = [
        s
        for s in metric.samples
        if all(
            (label in s.labels and s.labels[label] == label_value)
            for label, label_value in labels.items()
        )
    ]

    if value is not None:
        assert any(sample.value == value for sample in samples)

    assert samples


def text_string_to_metric_families_map(
    text,
) -> typing.Mapping[str, prometheus_client.Metric]:
    families: typing.Generator[
        prometheus_client.Metric
    ] = parser.text_string_to_metric_families(text)
    return {f.name: f for f in families}
