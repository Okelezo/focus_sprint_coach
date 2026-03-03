from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.settings import get_settings
from app.ui.router import ui_router


def create_app() -> FastAPI:
    settings = get_settings()

    if settings.sentry_dsn:
        import sentry_sdk

        def _before_send(event, hint):
            request = event.get("request") or {}
            request.pop("cookies", None)
            request.pop("headers", None)
            request.pop("data", None)
            event["request"] = request
            return event

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            before_send=_before_send,
            traces_sample_rate=0.0,
        )

    app = FastAPI(title=settings.app_name)

    if settings.cors_allow_origins:
        origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

    app.mount("/static", StaticFiles(directory="app/ui/static"), name="static")
    app.include_router(api_router)
    app.include_router(ui_router)

    return app


app = create_app()
