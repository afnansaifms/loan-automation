from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import documents
from app.core.database import Base, engine
from app.models import models  # noqa: F401
from app.routers import applications

app = FastAPI(title="Loan Automation Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(applications.router)
app.include_router(documents.router)

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)