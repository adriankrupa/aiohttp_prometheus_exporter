import asyncio
from types import SimpleNamespace
from typing import Type, Optional, Dict, Tuple

import aiohttp
import prometheus_client
from prometheus_client.registry import CollectorRegistry
from yarl import URL


class MetricsStore:
    def __init__(self, registry, namespace: str = None):
        self.requests_metrics = prometheus_client.Counter(
            name=f"aiohttp_client_requests",
            documentation="Total client requests by client name, method, scheme, remote and status code.",
            labelnames=["client_name", "method", "scheme", "remote", "status_code"],
            namespace=namespace,
            registry=registry,
        )

        self.requests_in_progress_metrics = prometheus_client.Gauge(
            name=f"aiohttp_client_requests_in_progress",
            documentation="Gauge of client requests by client name, method, scheme and remote currently being processed.",
            labelnames=["client_name", "method", "scheme", "remote"],
            namespace=namespace,
            registry=registry,
        )

        self.requests_processing_time_metrics = prometheus_client.Histogram(
            name=f"aiohttp_client_request_duration",
            documentation="Histogram of requests processing time by client name, method, scheme, remote and status code (in seconds).",
            labelnames=["client_name", "method", "scheme", "remote", "status_code"],
            unit="seconds",
            namespace=namespace,
            registry=registry,
        )

        self.requests_chunks_sent_metrics = prometheus_client.Counter(
            name=f"aiohttp_client_chunks_sent",
            documentation="Total bytes sent by client name (in bytes).",
            labelnames=["client_name"],
            unit="bytes",
            namespace=namespace,
            registry=registry,
        )

        self.requests_chunks_received_metrics = prometheus_client.Counter(
            name=f"aiohttp_client_chunks_received",
            documentation="Total bytes received by client name (in bytes).",
            labelnames=["client_name"],
            unit="bytes",
            namespace=namespace,
            registry=registry,
        )

        self.requests_exceptions_metrics = prometheus_client.Counter(
            name=f"aiohttp_client_requests_exceptions",
            documentation="Total client exceptions by client name, method, scheme, remote and exception name.",
            labelnames=["client_name", "method", "scheme", "remote", "exception_name"],
            namespace=namespace,
            registry=registry,
        )

        self.requests_redirect_metrics = prometheus_client.Counter(
            name=f"aiohttp_client_requests_redirect",
            documentation="Total client exceptions by client name, method, scheme, remote and exception name.",
            labelnames=["client_name", "method", "scheme", "remote", "status_code"],
            namespace=namespace,
            registry=registry,
        )

        self.connection_queued_time_metrics = prometheus_client.Histogram(
            name=f"aiohttp_client_connection_queued",
            documentation="Gauge of connection queue time by client name (in seconds).",
            labelnames=["client_name"],
            unit="seconds",
            namespace=namespace,
            registry=registry,
        )

        self.connection_create_time_metrics = prometheus_client.Histogram(
            name=f"aiohttp_client_connection_create",
            documentation="Gauge of connection create time by client name (in seconds).",
            labelnames=["client_name"],
            unit="seconds",
            namespace=namespace,
            registry=registry,
        )

        self.connection_reuseconn_metrics = prometheus_client.Counter(
            name=f"aiohttp_client_connection_reuseconn",
            documentation="Total reused connections.",
            labelnames=["client_name"],
            namespace=namespace,
            registry=registry,
        )

        self.dns_resolvehost_metrics = prometheus_client.Histogram(
            name=f"aiohttp_client_dns_resolvehost",
            documentation="Gauge of dsn resolving time by client name and host (in seconds).",
            labelnames=["client_name", "host"],
            unit="seconds",
            namespace=namespace,
            registry=registry,
        )

        self.dns_cache_hit_metrics = prometheus_client.Counter(
            name=f"aiohttp_client_dns_cache_hit",
            documentation="Total dns cache hits.",
            labelnames=["client_name", "host"],
            namespace=namespace,
            registry=registry,
        )

        self.dns_cache_miss_metrics = prometheus_client.Counter(
            name=f"aiohttp_client_dns_cache_miss",
            documentation="Total dns cache misses.",
            labelnames=["client_name", "host"],
            namespace=namespace,
            registry=registry,
        )


_metrics = {}  # type: Dict[Tuple[Optional[str], CollectorRegistry], MetricsStore]


def get_loop():
    return getattr(asyncio, "get_running_loop", asyncio.get_event_loop)()


class PrometheusTraceConfig(aiohttp.TraceConfig):
    def __init__(
        self,
        client_name="aiohttp_client",
        namespace=None,
        registry=None,
        trace_config_ctx_factory: Type[SimpleNamespace] = SimpleNamespace,
    ) -> None:
        super().__init__(trace_config_ctx_factory)

        if registry is None:
            registry = prometheus_client.REGISTRY

        if (namespace, registry) in _metrics:
            self.metrics = _metrics[(namespace, registry)]
        else:
            self.metrics = MetricsStore(registry=registry, namespace=namespace)
            _metrics[(namespace, registry)] = self.metrics

        self.client_name = client_name

        self.on_request_start.append(self.__on_request_start)
        self.on_request_end.append(self.__on_request_end)
        self.on_request_chunk_sent.append(self.__on_request_chunk_sent)
        self.on_response_chunk_received.append(self.__on_response_chunk_received)
        self.on_request_exception.append(self.__on_request_exception)
        self.on_request_redirect.append(self.__on_request_redirect)
        self.on_connection_queued_start.append(self.__on_connection_queued_start)
        self.on_connection_queued_end.append(self.__on_connection_queued_end)
        self.on_connection_create_start.append(self.__on_connection_create_start)
        self.on_connection_create_end.append(self.__on_connection_create_end)
        self.on_connection_reuseconn.append(self.__on_connection_reuseconn)
        self.on_dns_resolvehost_start.append(self.__on_dns_resolvehost_start)
        self.on_dns_resolvehost_end.append(self.__on_dns_resolvehost_end)
        self.on_dns_cache_hit.append(self.__on_dns_cache_hit)
        self.on_dns_cache_miss.append(self.__on_dns_cache_miss)

    async def __on_request_start(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestStartParams,
    ) -> None:
        loop = get_loop()

        trace_config_ctx._request_start_time = loop.time()

        self.metrics.requests_in_progress_metrics.labels(
            client_name=self.client_name,
            method=params.method,
            scheme=params.url.scheme,
            remote=params.url.host,
        ).inc()

    async def __on_request_end(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestEndParams,
    ) -> None:
        loop = get_loop()
        request_end_time = loop.time()

        request_start_time = getattr(
            trace_config_ctx, "_request_start_time", request_end_time
        )

        self.metrics.requests_in_progress_metrics.labels(
            client_name=self.client_name,
            method=params.method,
            scheme=params.url.scheme,
            remote=params.url.host,
        ).dec()

        self.metrics.requests_metrics.labels(
            client_name=self.client_name,
            method=params.response.method,
            scheme=params.response.url.scheme,
            remote=params.response.url.host,
            status_code=params.response.status,
        ).inc()

        self.metrics.requests_processing_time_metrics.labels(
            client_name=self.client_name,
            method=params.response.method,
            scheme=params.response.url.scheme,
            remote=params.response.url.host,
            status_code=params.response.status,
        ).observe(request_end_time - request_start_time)

    async def __on_request_chunk_sent(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestChunkSentParams,
    ) -> None:
        self.metrics.requests_chunks_sent_metrics.labels(
            client_name=self.client_name
        ).inc(len(params.chunk))

    async def __on_response_chunk_received(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceResponseChunkReceivedParams,
    ) -> None:
        self.metrics.requests_chunks_received_metrics.labels(
            client_name=self.client_name
        ).inc(len(params.chunk))

    async def __on_request_exception(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestExceptionParams,
    ) -> None:
        self.metrics.requests_exceptions_metrics.labels(
            client_name=self.client_name,
            method=params.method,
            scheme=params.url.scheme,
            remote=params.url.host,
            exception_name=type(params.exception).__name__,
        ).inc()

    async def __on_request_redirect(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceRequestRedirectParams,
    ) -> None:
        location = params.response.headers["Location"]
        new_url = URL(location)

        self.metrics.requests_in_progress_metrics.labels(
            client_name=self.client_name,
            method=params.method,
            scheme=params.url.scheme,
            remote=params.url.host,
        ).dec()

        self.metrics.requests_in_progress_metrics.labels(
            client_name=self.client_name,
            method=params.method,
            scheme=new_url.scheme,
            remote=new_url.host,
        ).inc()

        self.metrics.requests_metrics.labels(
            client_name=self.client_name,
            method=params.response.method,
            scheme=params.url.scheme,
            remote=params.url.host,
            status_code=params.response.status,
        ).inc()

        self.metrics.requests_redirect_metrics.labels(
            client_name=self.client_name,
            method=params.response.method,
            scheme=params.response.url.scheme,
            remote=params.response.url.host,
            status_code=params.response.status,
        ).inc()

    @staticmethod
    async def __on_connection_queued_start(
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceConnectionQueuedStartParams,
    ) -> None:
        loop = get_loop()
        trace_config_ctx._connection_queued_start_time = loop.time()

    async def __on_connection_queued_end(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceConnectionQueuedEndParams,
    ) -> None:
        loop = get_loop()
        connection_queued_end_time = loop.time()
        connection_queued_start_time = getattr(
            trace_config_ctx,
            "_connection_queued_start_time",
            connection_queued_end_time,
        )
        self.metrics.connection_queued_time_metrics.labels(
            client_name=self.client_name
        ).observe(connection_queued_end_time - connection_queued_start_time)

    @staticmethod
    async def __on_connection_create_start(
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceConnectionCreateStartParams,
    ) -> None:
        loop = get_loop()
        trace_config_ctx._connection_create_start_time = loop.time()

    async def __on_connection_create_end(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceConnectionCreateStartParams,
    ) -> None:
        loop = get_loop()
        connection_create_end_time = loop.time()
        connection_create_start_time = getattr(
            trace_config_ctx,
            "_connection_create_start_time",
            connection_create_end_time,
        )
        self.metrics.connection_create_time_metrics.labels(
            client_name=self.client_name
        ).observe(connection_create_end_time - connection_create_start_time)

    async def __on_connection_reuseconn(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceConnectionReuseconnParams,
    ) -> None:
        self.metrics.connection_reuseconn_metrics.labels(
            client_name=self.client_name
        ).inc()

    @staticmethod
    async def __on_dns_resolvehost_start(
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceDnsResolveHostStartParams,
    ) -> None:
        loop = get_loop()
        trace_config_ctx._dns_resolvehost_start_time = loop.time()

    async def __on_dns_resolvehost_end(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceDnsResolveHostEndParams,
    ) -> None:
        loop = get_loop()
        dns_resolvehost_end_time = loop.time()
        dns_resolvehost_start_time = getattr(
            trace_config_ctx, "_dns_resolvehost_start_time", dns_resolvehost_end_time
        )
        self.metrics.dns_resolvehost_metrics.labels(
            client_name=self.client_name, host=params.host
        ).observe(dns_resolvehost_end_time - dns_resolvehost_start_time)

    async def __on_dns_cache_hit(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceDnsCacheHitParams,
    ) -> None:
        self.metrics.dns_cache_hit_metrics.labels(
            client_name=self.client_name, host=params.host
        ).inc()

    async def __on_dns_cache_miss(
        self,
        session: aiohttp.ClientSession,
        trace_config_ctx: SimpleNamespace,
        params: aiohttp.TraceDnsCacheMissParams,
    ) -> None:
        self.metrics.dns_cache_miss_metrics.labels(
            client_name=self.client_name, host=params.host
        ).inc()
