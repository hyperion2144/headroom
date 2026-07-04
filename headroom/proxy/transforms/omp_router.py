"""OMP per-request upstream routing middleware.

When the ``headroom wrap omp`` command launches the proxy, it rewrites every
provider's ``baseUrl`` in ``models.yml`` to ``http://127.0.0.1:{port}`` so all
OMP traffic funnels through Headroom. The original upstream URLs are preserved
in a mapping file (``.omp/.headroom-upstreams.json``), keyed by model id.

:func:`OmpUpstreamRouterTransform` reads that mapping and, per request,
injects the ``x-headroom-base-url`` header based on the request's ``model``
field. Downstream handlers (Anthropic, OpenAI) honor the header via their
existing ``_resolve_*_upstream_base`` resolvers and route to the correct
upstream.

This is **not** a :class:`headroom.transforms.base.Transform` subclass —
those operate on parsed message lists and have no access to HTTP headers
or the request scope. Per-request upstream routing is HTTP-level
preprocessing, so it lives as FastAPI HTTP middleware instead. See
``bp/.../c3-proxy-extensions/design.md`` "Alternatives" for the rationale.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import Request, Response

logger = logging.getLogger("headroom.proxy")

#: Environment variable that points to the JSON mapping file.
_MAPPING_ENV_VAR = "HEADROOM_OMP_UPSTREAM_MAP"

#: Header injected to carry the per-request upstream base URL.
_HEADER_NAME = "x-headroom-base-url"

#: Threshold above which we log a warning for suspiciously large mappings.
#: OMP currently ships ~5 providers; anything north of 100 entries is almost
#: certainly a misconfiguration (e.g. an entire ``models.yml`` dumped in).
_MAPPING_WARN_SIZE = 100


class OmpUpstreamRouterTransform:
    """HTTP middleware that injects ``x-headroom-base-url`` per request.

    Constructed once at proxy startup when ``HEADROOM_OMP_UPSTREAM_MAP`` is
    set; the mapping is loaded from disk once and cached in memory. Each
    request reads the cached mapping, parses the request body's ``model``
    field, and (on a hit) injects the upstream URL into the request scope.

    **No-op conditions** (request passes through unchanged, no body read):

    - ``_mapping`` is empty — short-circuit before parsing the body
    - request body is not valid JSON — handler will surface its own error
    - request body is not a JSON object — no ``model`` field to look up
    - ``model`` field is missing or not a non-empty string
    - ``model`` is not present in the mapping

    **Body replay**: Starlette's :class:`~starlette.requests.Request` caches
    ``await request.body()`` internally (``self._body``), so downstream
    handlers calling :func:`headroom.proxy.helpers.read_request_json_with_bytes`
    or ``await request.body()`` again see the same bytes. No manual
    ``request._receive`` shim is required.
    """

    __slots__ = ("_mapping",)

    def __init__(
        self,
        mapping: dict[str, str] | None = None,
        mapping_path: str | os.PathLike[str] | None = None,
    ) -> None:
        """Initialize the transform.

        Args:
            mapping: Optional pre-built mapping. When provided, the env var
                and ``mapping_path`` are both ignored — used for tests and
                for callers that build the mapping in-process.
            mapping_path: Optional explicit path to a JSON mapping file. When
                ``None``, falls back to the ``HEADROOM_OMP_UPSTREAM_MAP`` env
                var. When neither is set, the transform constructs with an
                empty mapping (no-op).
        """
        if mapping is not None:
            self._mapping = _coerce_mapping(mapping)
            return

        path = mapping_path if mapping_path is not None else os.environ.get(_MAPPING_ENV_VAR)
        self._mapping = _load_mapping_file(path) if path else {}

    @property
    def mapping(self) -> dict[str, str]:
        """Return a copy of the loaded mapping (read-only snapshot)."""
        return dict(self._mapping)

    async def __call__(self, request: Request, call_next: Any) -> Response:
        """Inject ``x-headroom-base-url`` when the request's model is mapped.

        Behavior is documented in the class docstring; in short: this is a
        zero-overhead passthrough unless the mapping has entries AND the
        request body is a JSON object AND its ``model`` field matches one of
        those entries.
        """
        # Short-circuit: empty mapping → zero-overhead passthrough. No body
        # read, no JSON parse, no header injection. Non-OMP requests and
        # requests with an empty/missing mapping file never pay the cost.
        if not self._mapping:
            return await call_next(request)

        # Starlette caches `await request.body()` in `request._body`, so the
        # downstream handler can re-read it without us rewiring `_receive`.
        try:
            body_bytes = await request.body()
        except Exception:
            # Body read failure (client disconnected, etc.) — let downstream
            # surface the error rather than masking it.
            return await call_next(request)

        # Parse JSON. Malformed JSON → safe passthrough; the handler will
        # return its own 400 if the body is genuinely invalid.
        try:
            parsed = json.loads(body_bytes) if body_bytes else None
        except (json.JSONDecodeError, ValueError):
            return await call_next(request)

        if not isinstance(parsed, dict):
            return await call_next(request)

        model = parsed.get("model")
        if not isinstance(model, str) or not model:
            return await call_next(request)

        upstream = self._mapping.get(model)
        if upstream is None:
            return await call_next(request)

        # Inject header. Starlette's `Request.headers` is built lazily from
        # `scope["headers"]` on first access — and since this middleware runs
        # before the handler, the handler's first `request.headers.get(...)`
        # call will see the injected entry.
        new_header = (_HEADER_NAME.encode("utf-8"), upstream.encode("utf-8"))
        existing = list(request.scope.get("headers", []))
        existing.append(new_header)
        request.scope["headers"] = existing

        logger.debug(
            "omp_router_injected model=%s upstream=%s",
            model,
            upstream,
        )

        return await call_next(request)


def _load_mapping_file(path: str | os.PathLike[str]) -> dict[str, str]:
    """Load a JSON mapping file from disk.

    Returns an empty dict (no-op) when the file is missing, unreadable,
    empty, not valid JSON, or not a JSON object. The proxy MUST NOT crash
    on a corrupt upstream map; it MUST degrade to no-op routing — at worst
    the request falls back to ``ANTHROPIC_API_URL`` / ``OPENAI_API_URL``
    instead of the mapped upstream, which is observable but not catastrophic.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.debug("omp_router_mapping_file_missing path=%s", path)
        return {}
    except OSError as exc:
        logger.warning("omp_router_mapping_file_unreadable path=%s error=%s", path, exc)
        return {}

    if not text.strip():
        return {}

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("omp_router_mapping_file_invalid_json path=%s error=%s", path, exc)
        return {}

    if not isinstance(raw, dict):
        logger.warning("omp_router_mapping_file_not_object path=%s", path)
        return {}

    return _coerce_mapping(raw)


def _coerce_mapping(raw: dict[str, Any]) -> dict[str, str]:
    """Coerce a raw mapping to ``{str: str}``, dropping malformed entries.

    A mapping file produced by ``headroom wrap omp`` is always
    ``{model_id: upstream_base_url}`` (both strings). We drop entries with
    non-string keys or non-string values defensively — a corrupt entry
    shouldn't crash the proxy, it just won't route that one model.
    """
    mapping: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(key, str) and key and isinstance(value, str) and value:
            mapping[key] = value
    if len(mapping) > _MAPPING_WARN_SIZE:
        logger.warning(
            "omp_router_mapping_large count=%d threshold=%d",
            len(mapping),
            _MAPPING_WARN_SIZE,
        )
    return mapping
