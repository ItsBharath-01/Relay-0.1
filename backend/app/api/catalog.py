"""
catalog.py — Public catalog API routes (no auth required).
Separate router to avoid path conflict with /connections/{connection_id}.
"""
from typing import List
from fastapi import APIRouter, HTTPException
from app.catalog.apps import get_all_apps, get_app, AppDefinition

router = APIRouter(prefix="/catalog", tags=["Catalog"])


@router.get("", response_model=List[AppDefinition])
def list_catalog():
    """Returns all applications in the catalog (available and coming soon)."""
    return get_all_apps()


@router.get("/{app_id}", response_model=AppDefinition)
def get_catalog_app(app_id: str):
    """Returns a single application definition by app_id."""
    app = get_app(app_id)
    if not app:
        raise HTTPException(status_code=404, detail=f"App '{app_id}' not found in catalog.")
    return app
