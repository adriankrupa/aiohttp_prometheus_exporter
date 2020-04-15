from importlib import reload

import aiohttp
import asyncio
import prometheus_client
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient
from aiohttp.web_response import json_response
from prometheus_client.samples import Sample
from typing import Optional, List, Dict

import aiohttp_prometheus_exporter
from aiohttp_prometheus_exporter.trace import PrometheusTraceConfig


@pytest.fixture(autouse=True)
def clear_registry():
    yield

    reload(aiohttp_prometheus_exporter.trace.prometheus_client.registry)
    reload(aiohttp_prometheus_exporter.trace.prometheus_client.metrics)
    reload(aiohttp_prometheus_exporter.trace.prometheus_client)
    reload(aiohttp_prometheus_exporter.trace)


@pytest.fixture
def app():
    """ create a test app with various endpoints for the test scenarios """
    app = web.Application()
    routes = web.RouteTableDef()

    @routes.get("/200")
    async def response_200(_):
        return json_response({"message": "Hello World"})

    @routes.get("/redirect")
    async def redirect(_):
        raise web.HTTPFound("/200")

    app.router.add_routes(routes)

    return app


def registry_generator():
    return prometheus_client.CollectorRegistry(auto_describe=True)


@pytest.mark.parametrize(
    "namespace", [None, "namespace"], ids=["no_namespace", "custom_namespace"]
)
@pytest.mark.parametrize(
    "registry_gen",
    [None, registry_generator],
    ids=["default_registry", "custom_registry"],
)
@pytest.mark.parametrize(
    "client_name",
    ["aiohttp_client", "custom_client"],
    ids=["default_client_name", "custom_client_name"],
)
class TestTrace:
    @pytest.fixture
    def registry(self, registry_gen) -> Optional[prometheus_client.CollectorRegistry]:
        if registry_gen is None:
            return registry_gen
        return registry_gen()

    @pytest.fixture
    def current_registry(
        self, registry: prometheus_client.CollectorRegistry
    ) -> prometheus_client.CollectorRegistry:
        if registry:
            return registry
        return prometheus_client.REGISTRY

    @pytest.fixture
    def namespace_prefix(self, namespace):
        if namespace is None:
            return ""
        return f"{namespace}_"

    @pytest.fixture()
    async def client(
        self,
        aiohttp_client,
        app: web.Application,
        registry: prometheus_client.CollectorRegistry,
        namespace: Optional[str],
        client_name: Optional[str],
    ) -> TestClient:
        params = {}
        if registry:
            params["registry"] = registry
        if namespace is not None:
            params["namespace"] = namespace
        if client_name is not None:
            params["client_name"] = client_name
        return await aiohttp_client(
            app,
            trace_configs=[PrometheusTraceConfig(**params)],
            connector=aiohttp.TCPConnector(limit=1),
            timeout=aiohttp.ClientTimeout(total=0.05),
        )

    async def test_ok(
        self,
        client: TestClient,
        client_name: str,
        namespace_prefix: str,
        current_registry: prometheus_client.CollectorRegistry,
    ):
        response = await client.get("/200")
        await response.json()

        current_frozen_registry: List[prometheus_client.Metric] = list(
            current_registry.collect()
        )

        assert_metric_value(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_requests",
            f"{namespace_prefix}aiohttp_client_requests_total",
            1.0,
            labels={
                "client_name": client_name,
                "method": "GET",
                "scheme": "http",
                "remote": "127.0.0.1",
                "status_code": "200",
            },
        )

        assert_metric_value(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_requests_in_progress",
            f"{namespace_prefix}aiohttp_client_requests_in_progress",
            0.0,
            labels={
                "client_name": client_name,
                "method": "GET",
                "scheme": "http",
                "remote": "127.0.0.1",
            },
        )

        assert_metric_exists(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_request_duration_seconds",
            f"{namespace_prefix}aiohttp_client_request_duration_seconds_bucket",
            labels={
                "client_name": client_name,
                "method": "GET",
                "scheme": "http",
                "remote": "127.0.0.1",
            },
        )

        assert_metric_value(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_chunks_sent_bytes",
            f"{namespace_prefix}aiohttp_client_chunks_sent_bytes_total",
            0.0,
            labels={"client_name": client_name,},
        )

        assert_metric_value(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_chunks_received_bytes",
            f"{namespace_prefix}aiohttp_client_chunks_received_bytes_total",
            26.0,
            labels={"client_name": client_name,},
        )

        assert_metric_exists(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_connection_create_seconds",
            f"{namespace_prefix}aiohttp_client_connection_create_seconds_bucket",
            labels={"client_name": client_name,},
        )

    async def test_parallel_connection(
        self,
        client: TestClient,
        client_name: str,
        namespace_prefix: str,
        current_registry: prometheus_client.CollectorRegistry,
    ):
        results = await asyncio.gather(client.get("/200"), client.get("/200"))
        await asyncio.gather(*(r.json() for r in results))

        current_frozen_registry: List[prometheus_client.Metric] = list(
            current_registry.collect()
        )

        assert_metric_exists(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_connection_create_seconds",
            f"{namespace_prefix}aiohttp_client_connection_create_seconds_bucket",
            labels={"client_name": client_name,},
        )

        assert_metric_value(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_connection_reuseconn",
            f"{namespace_prefix}aiohttp_client_connection_reuseconn_total",
            1.0,
            labels={"client_name": client_name,},
        )

    async def test_redirect(
        self,
        client: TestClient,
        client_name: str,
        namespace_prefix: str,
        current_registry: prometheus_client.CollectorRegistry,
    ):
        response = await client.get("/redirect")
        await response.json()
        current_frozen_registry: List[prometheus_client.Metric] = list(
            current_registry.collect()
        )

        assert_metric_value(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_requests_redirect",
            f"{namespace_prefix}aiohttp_client_requests_redirect_total",
            1.0,
            labels={
                "client_name": client_name,
                "method": "GET",
                "scheme": "http",
                "remote": "127.0.0.1",
                "status_code": "302",
            },
        )

        assert_metric_value(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_requests",
            f"{namespace_prefix}aiohttp_client_requests_total",
            1.0,
            labels={
                "client_name": client_name,
                "method": "GET",
                "scheme": "http",
                "remote": "127.0.0.1",
                "status_code": "200",
            },
        )

        assert_metric_value(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_requests",
            f"{namespace_prefix}aiohttp_client_requests_total",
            1.0,
            labels={
                "client_name": client_name,
                "method": "GET",
                "scheme": "http",
                "remote": "127.0.0.1",
                "status_code": "302",
            },
        )

    async def test_exception(
        self,
        client: TestClient,
        client_name: str,
        namespace_prefix: str,
        current_registry: prometheus_client.CollectorRegistry,
    ):
        with pytest.raises(TypeError):
            response = await client.post("/200", data=TestClient)
            await response.json()
        current_frozen_registry: List[prometheus_client.Metric] = list(
            current_registry.collect()
        )

        assert_metric_value(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_requests_exceptions",
            f"{namespace_prefix}aiohttp_client_requests_exceptions_total",
            1.0,
            labels={
                "client_name": client_name,
                "method": "POST",
                "scheme": "http",
                "remote": "127.0.0.1",
                "exception_name": "TypeError",
            },
        )

    async def test_google(
        self,
        registry,
        namespace: str,
        namespace_prefix: str,
        client_name: str,
        current_registry: prometheus_client.CollectorRegistry,
    ):
        params = {}
        if registry:
            params["registry"] = registry
        if namespace is not None:
            params["namespace"] = namespace
        if client_name is not None:
            params["client_name"] = client_name

        connector = aiohttp.TCPConnector(ttl_dns_cache=300, force_close=True)

        async with aiohttp.ClientSession(
            trace_configs=[PrometheusTraceConfig(**params)], connector=connector
        ) as session:
            async with session.get("http://www.google.com/") as resp:
                assert resp.status

            async with session.get("http://www.google.com/") as resp:
                assert resp.status

        async with aiohttp.ClientSession(
            trace_configs=[PrometheusTraceConfig(**params)]
        ) as session:
            async with session.get("http://www.google.com/") as resp:
                assert resp.status

        current_frozen_registry: List[prometheus_client.Metric] = list(
            current_registry.collect()
        )

        assert_metric_exists(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_dns_resolvehost_seconds",
            f"{namespace_prefix}aiohttp_client_dns_resolvehost_seconds_bucket",
            labels={"client_name": client_name, "host": "www.google.com",},
        )

        assert_metric_exists(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_dns_cache_miss",
            f"{namespace_prefix}aiohttp_client_dns_cache_miss_total",
            labels={"client_name": client_name, "host": "www.google.com",},
        )

        assert_metric_exists(
            current_frozen_registry,
            f"{namespace_prefix}aiohttp_client_dns_cache_hit",
            f"{namespace_prefix}aiohttp_client_dns_cache_hit_total",
            labels={"client_name": client_name, "host": "www.google.com",},
        )


def get_metric_value(
    frozen_registry: List[prometheus_client.Metric],
    metric_label: str,
    sample_label: str,
    labels: Dict[str, str],
):
    for metric in frozen_registry:
        if metric.name != metric_label:
            continue
        for sample in metric.samples:  # type: Sample
            if sample.name != sample_label:
                continue
            if all(
                label in sample.labels and label_value == sample.labels[label]
                for label, label_value in labels.items()
            ):
                return sample.value


def assert_metric_value(
    frozen_registry: List[prometheus_client.Metric],
    metric_label: str,
    sample_label: str,
    expected_value: float,
    labels: Dict[str, str],
):
    value = get_metric_value(frozen_registry, metric_label, sample_label, labels)

    assert expected_value == value


def assert_metric_exists(
    frozen_registry: List[prometheus_client.Metric],
    metric_label: str,
    sample_label: str,
    labels: Dict[str, str],
):
    value = get_metric_value(frozen_registry, metric_label, sample_label, labels)

    assert value is not None
