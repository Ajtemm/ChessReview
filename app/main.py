"""Ulazna tačka servera (uvicorn app.main:app): FastAPI aplikacija, statički fajlovi,
rute iz app/web/routes.py i posao u pozadini iz app/web/background.py."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import load_config
from app.web.background import BackgroundServices
from app.web.routes import STATIC_DIR, router


@asynccontextmanager
async def lifespan(app: FastAPI):
    services = BackgroundServices(load_config())
    app.state.services = services
    services.start()
    yield
    services.stop()


app = FastAPI(title="Chess Review", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(router)
