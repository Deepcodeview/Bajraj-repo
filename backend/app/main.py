"""
main.py — FastAPI application entry point for Retail AI System.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.database.db import init_db
from app.routers.auth      import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.agents    import router as agents_router
from app.routers.camera    import router as camera_router
from app.routers.reports   import router as reports_router
from app.routers.websocket import router as ws_router
from app.routers.trends    import router as trends_router
from app.routers.sales     import router as sales_router
from app.routers.inventory import router as inventory_router
from app.routers.security  import router as security_router
from app.routers.enterprise  import router as enterprise_router
from app.routers.ai_insights import router as ai_router
from app.routers.staff       import router as staff_router
from app.routers.compliance  import router as compliance_router
from app.routers.engagement  import router as engagement_router
from app.routers.bi          import router as bi_router
from app.routers.platform    import router as platform_router
from app.routers.edge        import router as edge_router
from app.routers.face        import router as face_router
from app.routers.employees   import router as employees_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Retail AI System",
    description="Video analytics: footfall, zone dwell, shelf stock, AI agents.",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(agents_router)
app.include_router(camera_router)
app.include_router(reports_router)
app.include_router(ws_router)
app.include_router(trends_router)
app.include_router(sales_router)
app.include_router(inventory_router)
app.include_router(security_router)
app.include_router(enterprise_router)
app.include_router(ai_router)
app.include_router(staff_router)
app.include_router(compliance_router)
app.include_router(engagement_router)
app.include_router(bi_router)
app.include_router(platform_router)
app.include_router(edge_router)
app.include_router(face_router)
app.include_router(employees_router)
