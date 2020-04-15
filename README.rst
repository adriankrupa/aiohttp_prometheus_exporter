===========================
aiohttp prometheus exporter
===========================


.. image:: https://img.shields.io/pypi/v/aiohttp_prometheus_exporter.svg
        :target: https://pypi.python.org/pypi/aiohttp_prometheus_exporter

.. image:: https://img.shields.io/travis/adriankrupa/aiohttp_prometheus_exporter.svg
        :target: https://travis-ci.org/adriankrupa/aiohttp_prometheus_exporter

.. image:: https://img.shields.io/pypi/pyversions/aiohttp_prometheus_exporter.svg
        :target: https://pypi.python.org/pypi/aiohttp_prometheus_exporter

.. image:: https://img.shields.io/pypi/dm/aiohttp_prometheus_exporter.svg
        :target: https://pypi.python.org/pypi/aiohttp_prometheus_exporter

.. image:: https://codecov.io/gh/adriankrupa/aiohttp_prometheus_exporter/branch/master/graph/badge.svg
        :target: https://codecov.io/gh/adriankrupa/aiohttp_prometheus_exporter

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
         :target: https://github.com/psf/black
         :alt: Black

.. image:: https://readthedocs.org/projects/aiohttp-prometheus-exporter/badge/?version=latest
        :target: https://aiohttp-prometheus-exporter.readthedocs.io/en/latest/?badge=latest
        :alt: Documentation Status

.. image:: https://pyup.io/repos/github/adriankrupa/aiohttp_prometheus_exporter/shield.svg
         :target: https://pyup.io/repos/github/adriankrupa/aiohttp_prometheus_exporter/
         :alt: Updates

Export aiohttp metrics for Prometheus.io

Usage
*****

Requirements
------------

* aiohttp >= 3

Installation
------------

Install with:

.. code-block:: shell

    pip install aiohttp-prometheus-exporter

Server quickstart
-----------------

.. code-block:: python

    from aiohttp import web
    from aiohttp_prometheus_exporter.handler import metrics
    from aiohttp_prometheus_exporter.middleware import prometheus_middleware_factory

    async def hello(request):
        return web.Response(text="Hello, world")

    app = web.Application()
    app.add_routes([web.get('/', hello)])

    app.middlewares.append(prometheus_middleware_factory())
    app.router.add_get("/metrics", metrics())

    web.run_app(app)

Client quickstart
-----------------

.. code-block:: python

    import aiohttp
    from aiohttp_prometheus_exporter.trace import PrometheusTraceConfig

    async with aiohttp.ClientSession(trace_configs=[PrometheusTraceConfig()) as session:
        async with session.get('http://httpbin.org/get') as resp:
            print(resp.status)
            print(await resp.text())

Now, client metrics are attached to metrics exposed by your web server.

Credits
-------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
