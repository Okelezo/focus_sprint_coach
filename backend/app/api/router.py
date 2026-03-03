from fastapi import APIRouter

from app.api.routes.ai import router as ai_router
from app.api.routes.auth import router as auth_router
from app.api.routes.billing import router as billing_router
from app.api.routes.feedback import router as feedback_router
from app.api.routes.health import router as health_router
from app.api.routes.history import router as history_router
from app.api.routes.me import router as me_router
from app.api.routes.orchestrator import router as orchestrator_router
from app.api.routes.sprints import router as sprints_router
from app.api.routes.stats import router as stats_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.version import router as version_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(ai_router)
api_router.include_router(auth_router)
api_router.include_router(feedback_router)
api_router.include_router(billing_router)
api_router.include_router(me_router)
api_router.include_router(orchestrator_router)
api_router.include_router(tasks_router)
api_router.include_router(sprints_router)
api_router.include_router(history_router)
api_router.include_router(stats_router)
api_router.include_router(version_router)
