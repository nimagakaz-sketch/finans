import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel
from typing import Optional
from backend.database import (
    get_expenses_list,
    add_expense_record,
    delete_expense_record,
    delete_all_expenses,
    get_user_by_token,
    get_user_by_telegram_id,
    get_db
)
from backend.ai_service import scan_receipt_with_vision, parse_expense_text
from backend.config import UPLOAD_DIR

router = APIRouter(prefix="/api/expenses", tags=["expenses"])

class ExpenseCreate(BaseModel):
    amount: float
    category_id: str
    description: Optional[str] = "Расход"
    user_id: Optional[int] = 1
    family_id: Optional[int] = 1
    expense_date: Optional[str] = None
    receipt_url: Optional[str] = None
    receipt_meta: Optional[dict] = None

@router.get("")
async def list_expenses(
    family_id: int = 1,
    month: Optional[str] = None,
    user_id: Optional[int] = None,
    category: Optional[str] = None
):
    expenses = await get_expenses_list(family_id, month_prefix=month, user_id=user_id, category_id=category)
    return {"expenses": expenses, "count": len(expenses)}

@router.post("")
async def create_expense(expense: ExpenseCreate):
    record = await add_expense_record(
        family_id=expense.family_id,
        user_id=expense.user_id,
        amount=expense.amount,
        category_id=expense.category_id,
        description=expense.description,
        expense_date=expense.expense_date,
        receipt_url=expense.receipt_url,
        receipt_meta=expense.receipt_meta
    )
    return {"success": True, "expense": record}

@router.delete("/clear-all")
async def clear_all_expenses(family_id: int = 1):
    deleted_count = await delete_all_expenses(family_id)
    return {"success": True, "message": "Все расходы успешно обнулены", "deleted_count": deleted_count}

@router.delete("/{expense_id}")
async def delete_expense(expense_id: int, family_id: int = 1):
    success = await delete_expense_record(expense_id, family_id)
    if not success:
        raise HTTPException(status_code=404, detail="Расход не найден")
    return {"success": True, "deleted_id": expense_id}

@router.post("/scan-receipt")
async def scan_receipt(file: UploadFile = File(...)):
    filename = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = UPLOAD_DIR / filename
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    receipt_url = f"/uploads/receipts/{filename}"
    parsed_data = await scan_receipt_with_vision(content, filename)
    parsed_data["receipt_url"] = receipt_url
    return {"success": True, "receipt": parsed_data}

@router.post("/parse-text")
async def parse_text(text: str = Form(...)):
    parsed = await parse_expense_text(text)
    return {"success": True, "parsed": parsed}
