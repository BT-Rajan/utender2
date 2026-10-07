import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.i18n_server import current_language, generic_invalid, translate

logger = logging.getLogger("api")


def _format_validation_errors(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        # loc is like ("body", "email") — drop the leading "body"/"query"
        # marker so the message reads as a field name, not internal plumbing.
        field = ".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][-1])
        msg = str(err.get("msg", ""))
        if err.get("type") == "value_error" and msg.startswith("Value error, "):
            # Our own validators (e.g. "Payment stages must add up to 100%.")
            # already say what's wrong in plain words.
            parts.append(translate(msg[len("Value error, "):]))
        elif current_language.get() == "ar":
            parts.append(translate(generic_invalid(field)))
        else:
            parts.append(f"{field}: {msg}")
    return ("; " if current_language.get() == "en" else " ").join(dict.fromkeys(parts)) or translate("Invalid request.")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # FastAPI's default 422 body nests each error's loc/msg/type in a
        # list under "detail" — readable to a developer, not to the
        # end-user-facing message the frontend just displays verbatim.
        # Flatten it into one sentence instead.
        return JSONResponse(status_code=422, content={"detail": _format_validation_errors(exc)})

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        # Messages are written in English where they are raised; send them in
        # the language of the request (i18n_server). Machine codes such as
        # "not_approved" have no translation and pass through unchanged.
        detail = translate(exc.detail) if isinstance(exc.detail, str) else exc.detail
        return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Anything that reaches here is a bug, not an expected failure
        # (expected failures raise HTTPException with a specific status and
        # message). Log the real error server-side; never echo exception
        # internals back to the client.
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": translate("Internal server error.")})
