"""Port for outbound HTTP to a fixed list of public hosts (interface only)."""

from typing import Protocol

from app.domain.metadata import FetchedImage


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
