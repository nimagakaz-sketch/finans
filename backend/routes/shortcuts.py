from fastapi import APIRouter, HTTPException, Request, Body
from typing import Optional
from backend.database import get_user_by_token, add_expense_record, get_family_members
from backend.ai_service import parse_expense_text, rule_based_categorize
from backend.config import BOT_TOKEN

router = APIRouter(prefix="/api/shortcuts", tags=["shortcuts"])

# Global reference to bot instance if active
bot_instance = None

def set_bot_instance(bot):
    global bot_instance
    bot_instance = bot

@router.api_route("/add", methods=["GET", "POST"])
async def shortcut_add_expense(
    request: Request,
    token: Optional[str] = None,
    amount: Optional[float] = None,
    title: Optional[str] = None,
    query: Optional[str] = None
):
    """
    Endpoint for iOS Shortcuts (Команды на iPhone).
    Can receive query parameters, JSON, or form-data.
    """
    # Parse incoming data from query params or JSON body
    if request.method == "POST":
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
                token = body.get("token") or token
                amount = body.get("amount") if body.get("amount") is not None else amount
                title = body.get("title") or body.get("description") or title
                query = body.get("query") or body.get("text") or query
            except Exception:
                pass
        elif "form" in content_type:
            form = await request.form()
            token = form.get("token") or token
            amount = float(form.get("amount")) if form.get("amount") else amount
            title = form.get("title") or form.get("description") or title
            query = form.get("query") or form.get("text") or query

    if not token:
        raise HTTPException(status_code=400, detail="Отсутствует token. Скопируйте персональный токен из настроек.")

    user = await get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=403, detail="Неверный токен авторизации.")

    # Determine amount, category, and description
    final_amount = amount
    final_desc = title or ""

    if query and (final_amount is None or not final_desc):
        parsed = await parse_expense_text(query)
        if final_amount is None:
            final_amount = parsed["amount"]
        if not final_desc:
            final_desc = parsed["description"]
        category_id = parsed["category_id"]
    elif final_desc:
        category_id = rule_based_categorize(final_desc)
    else:
        category_id = "other"
        final_desc = "Расход через iOS Команду"

    if final_amount is None or final_amount <= 0:
        raise HTTPException(status_code=400, detail="Не удалось определить сумму расхода.")

    # Save to database
    expense = await add_expense_record(
        family_id=user["family_id"],
        user_id=user["id"],
        amount=final_amount,
        category_id=category_id,
        description=final_desc
    )

    formatted_amount = f"{final_amount:,.0f} ₽".replace(",", " ")
    cat_name = expense.get("category_name", "Расход")
    cat_icon = expense.get("category_icon", "💳")
    user_name = user.get("first_name", "Супруг")

    msg = f"✅ Записано: {formatted_amount} — {cat_icon} {cat_name} ({final_desc})"

    # Notify partner in Telegram if bot is running
    if bot_instance and BOT_TOKEN:
        try:
            members = await get_family_members(user["family_id"])
            partner = next((m for m in members if m["id"] != user["id"]), None)
            if partner and partner["id"] > 100:  # Valid Telegram ID
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
        "message": msg,
        "amount": final_amount,
        "category": cat_name,
        "category_id": category_id,
        "description": final_desc,
        "user": user_name,
        "expense_id": expense["id"]
    }
