"""Port for outbound HTTP to a fixed list of public hosts (interface only)."""

from typing import Protocol

from app.domain.metadata import FetchedImage
from app.domain.release import ConditionalJson


class HttpGateway(Protocol):
    """The only way the app talks to the outside. Implementations must refuse any host that is not
    on their fixed allowlist and enforce size, time and content-type limits.

    Every failure (refused URL, network, timeout, too large, wrong content type, bad JSON) is an
    `ExternalFetchError` with a generic reason code; nothing else escapes.
    """

    def get_json(self, url: str) -> object:
        """GET and parse a JSON document."""
        ...

    def post_json(self, url: str, payload: dict[str, object]) -> object:
        """POST a JSON body (GraphQL) and parse the JSON answer."""
        ...

    def get_image(self, url: str) -> FetchedImage:
        """GET an image (jpeg, png or webp, checked by magic bytes)."""
        ...

    def get_json_conditional(self, url: str, etag: str | None) -> ConditionalJson:
        """GET a JSON document with `If-None-Match: <etag>` (when given). Returns the status
        (200, 304, or a throttling 403/429 with its rate-limit headers) instead of raising for
        those; every other failure is an `ExternalFetchError`. Short timeouts, never waits long."""
        ...
