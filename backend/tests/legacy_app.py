"""PR8 삭제 전 옛 라우터를 독립 검증합니다. 운영 앱에는 등록하지 않습니다."""

from app.api.v1.routes import router
from app.main import create_app as current_app


def create_app(**kwargs):
    app = current_app(**kwargs)
    app.router.routes[:] = [
        r
        for r in app.router.routes
        if getattr(r, "path", "")
        in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc", "/health"}
    ]
    app.include_router(router)
    return app
