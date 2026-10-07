import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.config import get_settings
from app.error_handlers import register_error_handlers
from app.middleware import LanguageMiddleware, MaxBodySizeMiddleware
from app.routers.admin import router as admin_router
from app.routers.account import router as account_router
from app.routers.billing import router as billing_router
from app.routers.categories import router as categories_router
from app.routers.clarifications import router as clarifications_router
from app.routers.service_provider import router as service_provider_router
from app.routers.cron import router as cron_router
from app.routers.files import router as files_router
from app.routers.notifications import router as notifications_router
from app.routers.offers import router as offers_router
from app.routers.owner import router as owner_router
from app.routers.projects import router as projects_router
from app.routers.public import router as public_router

settings = get_settings()

app = FastAPI(title="U-Tender API")

register_error_handlers(app)

app.add_middleware(MaxBodySizeMiddleware, max_body_bytes=settings.max_upload_mb * 1024 * 1024)
app.add_middleware(LanguageMiddleware)


# Stage 4.3 follow-up: the server's clock on every response, so the interface
# counts time to a deadline from the same clock that enforces it -- not from
# a device clock that may be wrong.
@app.middleware("http")
async def server_time(request, call_next):
    response = await call_next(request)
    response.headers["X-Server-Time"] = str(int(time.time() * 1000))
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Server-Time"],
)

app.include_router(auth_router)
app.include_router(account_router)
app.include_router(public_router)
app.include_router(projects_router)
app.include_router(categories_router)
app.include_router(clarifications_router)
app.include_router(offers_router)
app.include_router(owner_router)
app.include_router(service_provider_router)
app.include_router(admin_router)
app.include_router(billing_router)
app.include_router(cron_router)
app.include_router(files_router)
app.include_router(notifications_router)


@app.get("/health")
def health():
    return {"ok": True}
