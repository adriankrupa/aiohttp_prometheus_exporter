import prometheus_client
from aiohttp import web


def metrics(registry: prometheus_client.CollectorRegistry = None):
    async def handler(_):
        prom_registry = registry if registry else prometheus_client.REGISTRY

        response = web.Response(body=prometheus_client.generate_latest(prom_registry))
        response.content_type = prometheus_client.CONTENT_TYPE_LATEST
        return response

    return handler
