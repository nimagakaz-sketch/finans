from fastapi import APIRouter
from typing import Optional
from backend.database import get_family_monthly_analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

@router.get("/monthly")
async def get_monthly_analytics(family_id: int = 1, month: Optional[str] = None):
    data = await get_family_monthly_analytics(family_id, month_prefix=month)
    return data
