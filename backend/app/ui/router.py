from fastapi import APIRouter

from app.ui.routes.app_pages import router as app_pages_router
from app.ui.routes.auth_pages import router as auth_pages_router
from app.ui.routes.billing_pages import router as billing_pages_router
from app.ui.routes.sprint_pages import router as sprint_pages_router

ui_router = APIRouter()
ui_router.include_router(auth_pages_router)
ui_router.include_router(app_pages_router)
ui_router.include_router(billing_pages_router)
ui_router.include_router(sprint_pages_router)
