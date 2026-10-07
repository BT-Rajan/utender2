from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class LanguageMiddleware:
    """Holds the language of the request (Accept-Language: en | ar, sent by
    the interface) for the duration of the request, so the server's own
    messages are sent in it (app.i18n_server)."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from app.i18n_server import current_language, language_from

        token = current_language.set(language_from(Headers(scope=scope).get("accept-language")))
        try:
            await self.app(scope, receive, send)
        finally:
            current_language.reset(token)


class MaxBodySizeMiddleware:
    """Caps request bodies (file uploads included) at the configured size --
    the Python equivalent of the original app's explicit Server Action body
    size limit (raised to 50MB there to fit zipped drawing folders).

    Two layers: a declared Content-Length over the cap is rejected before any
    body is read; and because chunked requests carry no Content-Length at all
    (and a header can lie), the bytes actually received are counted too, so
    the cap holds however the body arrives. Pure ASGI rather than
    BaseHTTPMiddleware because the latter can't wrap the receive channel."""

    def __init__(self, app: ASGIApp, max_body_bytes: int):
        self.app = app
        self.max_body_bytes = max_body_bytes

    def _too_large(self) -> HTTPException:
        return HTTPException(status_code=413, detail=f"Request body too large \u2014 max {self.max_body_bytes // (1024 * 1024)}MB.")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_body_bytes:
                    exc = self._too_large()
                    from app.i18n_server import language_from, translate

                    detail = translate(exc.detail, language_from(Headers(scope=scope).get("accept-language")))
                    await JSONResponse(status_code=exc.status_code, content={"detail": detail})(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    # An HTTPException raised while the app reads the body is
                    # turned into a normal 413 by the framework's handler.
                    raise self._too_large()
            return message

        await self.app(scope, counting_receive, send)
