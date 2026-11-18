from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.database import (
    get_incomes_list,
    add_income_record,
    delete_income_record,
    delete_all_incomes,
    DEFAULT_INCOME_SOURCES
)

router = APIRouter(prefix="/api/incomes", tags=["incomes"])

class IncomeCreate(BaseModel):
    amount: float
    source: Optional[str] = "Зарплата"
    description: Optional[str] = "Доход"
    user_id: Optional[int] = 1
    family_id: Optional[int] = 1
    income_date: Optional[str] = None

@router.get("")
async def list_incomes(
    family_id: int = 1,
    month: Optional[str] = None,
    user_id: Optional[int] = None
):
    incomes = await get_incomes_list(family_id, month_prefix=month, user_id=user_id)
    return {"incomes": incomes, "count": len(incomes)}

@router.get("/sources")
async def list_sources():
    return {"sources": DEFAULT_INCOME_SOURCES}

@router.post("")
async def create_income(income: IncomeCreate):
    record = await add_income_record(
        family_id=income.family_id,
        user_id=income.user_id,
        amount=income.amount,
        source=income.source,
        description=income.description,
        income_date=income.income_date
    )
    return {"success": True, "income": record}

@router.delete("/clear-all")
async def clear_all_incomes_endpoint(family_id: int = 1):
    deleted_count = await delete_all_incomes(family_id)
    return {"success": True, "message": "Все доходы успешно обнулены", "deleted_count": deleted_count}

@router.delete("/{income_id}")
async def delete_income(income_id: int, family_id: int = 1):
    success = await delete_income_record(income_id, family_id)
    if not success:
        raise HTTPException(status_code=404, detail="Доход не найден")
    return {"success": True, "deleted_id": income_id}
