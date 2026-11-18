from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from backend.database import (
    get_family_by_id,
    get_family_members,
    get_db,
    DEFAULT_CATEGORIES
)

router = APIRouter(prefix="/api/family", tags=["family"])

class BudgetUpdate(BaseModel):
    family_id: int
    monthly_budget: float

@router.get("/me")
async def get_my_family(family_id: int = 1, user_id: int = 1):
    family = await get_family_by_id(family_id)
    if not family:
        raise HTTPException(status_code=404, detail="Семья не найдена")
    members = await get_family_members(family_id)
    me = next((m for m in members if m["id"] == user_id), members[0] if members else None)
    partner = next((m for m in members if m["id"] != user_id), None)

    return {
        "family": family,
        "me": me,
        "partner": partner,
        "members": members,
        "invite_code": family["invite_code"]
    }

@router.get("/categories")
async def list_categories():
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM categories ORDER BY id ASC")
        rows = await cursor.fetchall()
        return {"categories": [dict(r) for r in rows]}

@router.post("/budget")
async def update_budget(payload: BudgetUpdate):
    async with get_db() as db:
        await db.execute(
            "UPDATE families SET monthly_budget = ? WHERE id = ?",
            (payload.monthly_budget, payload.family_id)
        )
        await db.commit()
    return {"success": True, "monthly_budget": payload.monthly_budget}
