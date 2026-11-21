from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.http_utils import header, is_api_path, send_json_error

TOO_LARGE_DETAIL = "Request body too large"
BAD_LENGTH_DETAIL = "Invalid Content-Length"


class BodySizeLimitMiddleware:
    """Refuses oversized request bodies under /api with a generic 413.

    Two checks: a declared `Content-Length` above the limit is refused before the app runs, and the
    bytes actually received are counted, so a chunked/streamed body without `Content-Length`
    (or one that lies about it) is cut as soon as it crosses the limit. When that happens the app
    sees a disconnect, anything it tries to answer is discarded, and the client gets the 413.
    The API only takes small JSON documents; there are no uploads.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self._max = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_api_path(scope["path"]):
            await self.app(scope, receive, send)
            return

        declared = header(scope, b"content-length")
        if declared is not None:
            if not (declared.isascii() and declared.isdigit()):
                await send_json_error(send, 400, BAD_LENGTH_DETAIL)
                return
            if int(declared) > self._max:
                await send_json_error(send, 413, TOO_LARGE_DETAIL)
                return

        received = 0
        exceeded = False
        responded = False  # the app started its own response before the limit was crossed

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max:
                    exceeded = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal responded
            if exceeded:
                return  # discard whatever the app produced after the cut
            if message["type"] == "http.response.start":
                responded = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not exceeded:
                raise
            # The app failed because we cut its input; that failure is expected.
        if exceeded and not responded:
            await send_json_error(send, 413, TOO_LARGE_DETAIL)
