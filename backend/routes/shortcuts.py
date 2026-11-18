import re
from fastapi import APIRouter, HTTPException, Request, Body
from typing import Optional
from backend.database import get_user_by_token, add_expense_record, add_income_record, get_family_members
from backend.ai_service import parse_expense_text, rule_based_categorize
from backend.config import BOT_TOKEN

router = APIRouter(prefix="/api/shortcuts", tags=["shortcuts"])

bot_instance = None

def set_bot_instance(bot):
    global bot_instance
    bot_instance = bot

@router.api_route("/add", methods=["GET", "POST"])
async def shortcut_add_transaction(
    request: Request,
    token: Optional[str] = None,
    amount: Optional[float] = None,
    title: Optional[str] = None,
    query: Optional[str] = None,
    type: Optional[str] = None  # "expense" or "income"
):
    """
    Endpoint for iOS Shortcuts (Команды на iPhone).
    Supports both Expenses and Incomes (Приход денег).
    """
    if request.method == "POST":
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
                token = body.get("token") or token
                amount = body.get("amount") if body.get("amount") is not None else amount
                title = body.get("title") or body.get("description") or title
                query = body.get("query") or body.get("text") or query
                type = body.get("type") or type
            except Exception:
                pass
        elif "form" in content_type:
            form = await request.form()
            token = form.get("token") or token
            amount = float(form.get("amount")) if form.get("amount") else amount
            title = form.get("title") or form.get("description") or title
            query = form.get("query") or form.get("text") or query
            type = form.get("type") or type

    if not token:
        raise HTTPException(status_code=400, detail="Отсутствует token. Скопируйте персональный токен из настроек.")

    user = await get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=403, detail="Неверный токен авторизации.")

    raw_check = f"{title or ''} {query or ''}".lower()
    is_income = type == "income" or (query and query.strip().startswith("+")) or any(
        w in raw_check for w in ["доход", "зарплат", "преми", "аванс", "подработк", "кэшбэк", "приход"]
    )

    final_amount = amount
    final_desc = title or ""

    if query and (final_amount is None or not final_desc):
        parsed = await parse_expense_text(query.lstrip("+"))
        if final_amount is None:
            final_amount = parsed["amount"]
        if not final_desc:
            final_desc = parsed["description"]

    if final_amount is None or final_amount <= 0:
        raise HTTPException(status_code=400, detail="Не удалось определить сумму.")

    formatted_amount = f"{final_amount:,.0f} ₽".replace(",", " ")
    user_name = user.get("first_name", "Супруг")

    if is_income:
        # Determine source
        source = "Зарплата"
        if "преми" in raw_check:
            source = "Премия"
        elif "аванс" in raw_check:
            source = "Аванс"
        elif "подработк" in raw_check:
            source = "Подработка"
        elif "кэшбэк" in raw_check:
            source = "Кэшбэк/Проценты"
        elif "подарок" in raw_check:
            source = "Подарок"

        income = await add_income_record(
            family_id=user["family_id"],
            user_id=user["id"],
            amount=final_amount,
            source=source,
            description=final_desc or source
        )

        msg = f"💰 Доход записан: +{formatted_amount} ({source})"

        if bot_instance and BOT_TOKEN:
            try:
                members = await get_family_members(user["family_id"])
                partner = next((m for m in members if m["id"] != user["id"]), None)
                if partner and partner["id"] > 100:
                    partner_text = (
                        f"💵 <b>Пополнение бюджета от {user_name}!</b>\n"
                        f"💰 <b>+{formatted_amount}</b>\n"
                        f"📁 Источник: {source}\n"
                        f"📝 {final_desc}"
                    )
                    await bot_instance.send_message(chat_id=partner["id"], text=partner_text, parse_mode="HTML")
            except Exception as e:
                print(f"Partner notification error: {e}")

        return {
            "success": True,
            "type": "income",
            "message": msg,
            "amount": final_amount,
            "source": source,
            "description": final_desc,
            "user": user_name,
            "id": income["id"]
        }

    else:
        category_id = rule_based_categorize(final_desc)
        expense = await add_expense_record(
            family_id=user["family_id"],
            user_id=user["id"],
            amount=final_amount,
            category_id=category_id,
            description=final_desc or "Расход"
        )

        cat_name = expense.get("category_name", "Расход")
        cat_icon = expense.get("category_icon", "💳")

        msg = f"✅ Записано: {formatted_amount} — {cat_icon} {cat_name} ({final_desc})"

        if bot_instance and BOT_TOKEN:
            try:
                members = await get_family_members(user["family_id"])
                partner = next((m for m in members if m["id"] != user["id"]), None)
                if partner and partner["id"] > 100:
                    partner_text = (
                        f"📲 <b>Новый расход от {user_name}!</b>\n"
                        f"💰 <b>{formatted_amount}</b>\n"
                        f"📁 {cat_icon} {cat_name}\n"
                        f"📝 {final_desc}"
                    )
                    await bot_instance.send_message(chat_id=partner["id"], text=partner_text, parse_mode="HTML")
            except Exception as e:
                print(f"Partner notification error: {e}")

        return {
            "success": True,
            "type": "expense",
            "message": msg,
            "amount": final_amount,
            "category": cat_name,
            "category_id": category_id,
            "description": final_desc,
            "user": user_name,
            "expense_id": expense["id"]
        }
