"""Proxy-level HTTP transforms (FastAPI middleware).

Distinct from:

- :mod:`headroom.transforms` — message-level ``Transform`` ABC that operates
  on parsed message lists via ``apply(messages, tokenizer, **kwargs)``.
  Transforms have no access to the HTTP request scope, so they cannot inject
  headers.
- :mod:`headroom.proxy.interceptors` — tool-result interceptors that rewrite a
  single ``tool_result`` text block before it reaches the model.

This package holds HTTP-level preprocessing middleware for the proxy. The
canonical example is :class:`OmpUpstreamRouterTransform`, which reads a
model→upstream mapping and injects ``x-headroom-base-url`` per request so
multi-provider OMP-wrapped clients route to the correct upstream.
"""
