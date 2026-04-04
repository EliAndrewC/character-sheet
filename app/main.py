"""L7R Character Builder — FastAPI application entry point."""

import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import init_db
from app.routes import characters, pages

app = FastAPI(title="L7R Character Builder")

# Templates
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)

# Static files
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")),
    name="static",
)

# Routes
app.include_router(pages.router)
app.include_router(characters.router)


@app.on_event("startup")
def on_startup():
    init_db()
