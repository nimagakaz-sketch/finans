import secrets
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from backend.database import (
    get_family_by_id,
    get_family_members,
    update_family_name,
    update_user_profile,
    update_user_token,
    get_db,
    DEFAULT_CATEGORIES
)

router = APIRouter(prefix="/api/family", tags=["family"])

class BudgetUpdate(BaseModel):
    family_id: int
    monthly_budget: float

class FamilyRename(BaseModel):
    family_id: int
    name: str

class MemberUpdate(BaseModel):
    user_id: int
    first_name: str
    role: Optional[str] = None

class TokenUpdate(BaseModel):
    user_id: int
    token: str

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

@router.put("/rename")
async def rename_family(payload: FamilyRename):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Название семьи не может быть пустым")
    family = await update_family_name(payload.family_id, payload.name)
    return {"success": True, "family": family}

@router.put("/member")
async def update_member(payload: MemberUpdate):
    if not payload.first_name.strip():
        raise HTTPException(status_code=400, detail="Имя не может быть пустым")
    user = await update_user_profile(payload.user_id, payload.first_name, payload.role)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {"success": True, "user": user}

@router.post("/token")
async def update_token(payload: TokenUpdate):
    try:
        user = await update_user_token(payload.user_id, payload.token)
        return {"success": True, "user": user, "token": user["api_token"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/token/generate")
async def generate_new_token(user_id: int = 1):
    new_token = "tok_" + secrets.token_hex(8)
    user = await update_user_token(user_id, new_token)
    return {"success": True, "token": new_token, "user": user}

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
