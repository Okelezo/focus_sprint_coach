from fastapi import APIRouter

from app.core.settings import get_settings

router = APIRouter(tags=["meta"])


@router.get("/version")
async def version() -> dict[str, str | None]:
    settings = get_settings()
    sha = settings.railway_git_commit_sha or settings.git_sha
    return {
        "git_sha": sha,
        "build_time": settings.build_time,
        "env": settings.environment,
    }
