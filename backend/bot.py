import os
import uuid
import re
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from backend.config import BOT_TOKEN, WEBAPP_URL, UPLOAD_DIR
from backend.database import (
    get_user_by_telegram_id,
    create_user_and_family,
    join_family_by_code,
    add_expense_record,
    add_income_record,
    delete_all_expenses,
    get_family_by_id,
    get_family_members,
    get_family_monthly_analytics,
    delete_expense_record,
    update_family_name,
    update_user_profile,
    update_user_token
)
from backend.ai_service import parse_expense_text, scan_receipt_with_vision
from backend.routes.shortcuts import set_bot_instance

dp = Dispatcher()
bot = None

def get_main_keyboard():
    webapp_btn = KeyboardButton(
        text="💎 Открыть трекер",
        web_app=WebAppInfo(url=f"{WEBAPP_URL}/")
    )
    return ReplyKeyboardMarkup(
        keyboard=[
            [webapp_btn],
            [KeyboardButton(text="📊 Сводка (доходы/траты)"), KeyboardButton(text="📲 Команды на iPhone")],
            [KeyboardButton(text="🔗 Пригласить супругу"), KeyboardButton(text="⚙️ Настройки семьи")]
        ],
        resize_keyboard=True
    )

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    tg_id = message.from_user.id
    first_name = message.from_user.first_name or "Пользователь"
    username = message.from_user.username

    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    invite_code = None
    if args and args[0].startswith("join_"):
        invite_code = args[0].replace("join_", "").strip()

    user = await get_user_by_telegram_id(tg_id)

    if invite_code:
        user = await join_family_by_code(tg_id, invite_code, first_name, username, role="Супруга")
        if user:
            family = await get_family_by_id(user["family_id"])
            await message.answer(
                f"🎉 <b>Добро пожаловать в семейный бюджет!</b>\n\n"
                f"Вы успешно подключились к семье: <b>{family['name']}</b>.\n"
                f"Теперь вы вдвоем можете быстро вносить траты, приходы денег, отправлять фото чеков и сразу видеть баланс!",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            members = await get_family_members(user["family_id"])
            spouse = next((m for m in members if m["id"] != tg_id), None)
            if spouse and bot:
                await bot.send_message(
                    chat_id=spouse["id"],
                    text=f"💞 <b>{first_name}</b> присоединилась к семейному трекеру!",
                    parse_mode="HTML"
                )
            return
        else:
            await message.answer("⚠️ Код приглашения не найден или устарел.")

    if not user:
        user = await create_user_and_family(tg_id, first_name, username, role="Супруг")

    family = await get_family_by_id(user["family_id"])
    members = await get_family_members(user["family_id"])
    partner = next((m for m in members if m["id"] != tg_id), None)

    welcome_text = (
        f"👋 <b>Привет, {first_name}!</b>\n\n"
        f"Это <b>Семейный трекер финансов и общих трат с чеками</b>.\n\n"
        f"⚡️ <b>Как быстро записать:</b>\n"
        f"• <b>Расход:</b> <code>1500 продукты</code> или <code>Бензин 2500</code>\n"
        f"• <b>Приход денег:</b> <code>+50000 зарплата</code> или <code>доход 30000</code>\n"
        f"• <b>Чек:</b> отправьте фото кассового чека — бот распознает сумму сам!\n"
        f"• <b>iPhone Команда:</b> быстрый ввод с экрана блокировки или Action Button.\n\n"
        f"👥 <b>Семья:</b> {family['name']}\n"
        f"👤 <b>Партнер:</b> {partner['first_name'] if partner else 'Еще не подключен(а)'}\n"
    )

    if not partner:
        bot_info = await bot.get_me() if bot else None
        bot_user = bot_info.username if bot_info else "FamilyFinanceBot"
        invite_link = f"https://t.me/{bot_user}?start=join_{family['invite_code']}"
        welcome_text += f"\n🔗 <b>Ссылка для подключения супруги:</b>\n{invite_link}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Открыть трекер (Mini App)", web_app=WebAppInfo(url=f"{WEBAPP_URL}/"))],
        [InlineKeyboardButton(text="📲 Настроить iPhone Команду", callback_data="show_shortcuts")]
    ])

    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())
    await message.answer("Нажмите кнопку ниже, чтобы открыть стеклянное приложение:", reply_markup=kb)

@dp.message(F.text == "📊 Сводка (доходы/траты)")
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        user = await create_user_and_family(message.from_user.id, message.from_user.first_name)

    stats = await get_family_monthly_analytics(user["family_id"])
    currency = stats["currency"]
    spent_str = f"{stats['total_spent']:,.0f} {currency}".replace(",", " ")
    income_str = f"{stats['total_income']:,.0f} {currency}".replace(",", " ")
    net_str = f"{stats['net_balance']:,.0f} {currency}".replace(",", " ")

    lines = [
        f"📊 <b>Сводка за {stats['month']} ({stats['family_name']}):</b>\n",
        f"🟢 <b>Общий доход:</b> <b>+{income_str}</b>",
        f"🔴 <b>Всего расходов:</b> <b>{spent_str}</b> (лимит: {stats['monthly_budget']:,.0f} {currency})".replace(",", " "),
        f"💎 <b>Остаток / Накопления:</b> <b>{net_str}</b>\n",
        "👥 <b>Расходы по участникам:</b>"
    ]

    for u in stats["users"]:
        u_total = f"{u['total_user']:,.0f} {currency}".replace(",", " ")
        lines.append(f"• {u['first_name']}: {u_total}")

    if stats.get("split") and stats["split"]["payer"]:
        lines.append(f"\n⚖️ <b>Баланс 50/50:</b>\n👉 {stats['split']['text']}")

    if stats["categories"]:
        lines.append("\n📁 <b>Топ категорий трат:</b>")
        for cat in stats["categories"][:5]:
            cat_tot = f"{cat['total']:,.0f} {currency}".replace(",", " ")
            lines.append(f"• {cat['icon']} {cat['name']}: {cat_tot} ({cat['percentage']}%)")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Подробная аналитика в приложении", web_app=WebAppInfo(url=f"{WEBAPP_URL}/"))]
    ])

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)

@dp.message(F.text == "⚙️ Настройки семьи")
@dp.message(Command("settings"))
async def cmd_settings(message: types.Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        user = await create_user_and_family(message.from_user.id, message.from_user.first_name)

    family = await get_family_by_id(user["family_id"])
    members = await get_family_members(user["family_id"])

    text = (
        f"⚙️ <b>Настройки семьи: {family['name']}</b>\n\n"
        f"👤 <b>Ваше имя:</b> {user['first_name']} ({user['role']})\n"
        f"🔑 <b>Ваш API токен:</b> <code>{user['api_token']}</code>\n\n"
        f"<b>Быстрые команды бота:</b>\n"
        f"• <code>/name [НовоеИмя]</code> — изменить свое имя\n"
        f"• <code>/family [НоваяФамилия]</code> — изменить название семьи\n"
        f"• <code>/token [НовыйТокен]</code> — установить свой персональный токен\n"
        f"• <code>/clear_expenses</code> — обнулить все покупки семьи"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Обнулить все покупки", callback_data="ask_clear_all")],
        [InlineKeyboardButton(text="💎 Открыть настройки в приложении", web_app=WebAppInfo(url=f"{WEBAPP_URL}/"))]
    ])

    await message.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.message(Command("clear_expenses"))
async def cmd_clear_expenses(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, удалить все траты", callback_data="confirm_clear_all")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])
    await message.answer(
        "⚠️ <b>Внимание!</b>\nВы действительно хотите полностью обнулить все сохраненные расходы семьи?",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(F.data == "ask_clear_all")
async def cb_ask_clear_all(callback: types.CallbackQuery):
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, удалить все покупки", callback_data="confirm_clear_all")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])
    await callback.message.edit_text(
        "⚠️ <b>Подтверждение обнуления</b>\nВы уверены? Все покупки семьи будут безвозвратно удалены.",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(F.data == "confirm_clear_all")
async def cb_confirm_clear_all(callback: types.CallbackQuery):
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user:
        count = await delete_all_expenses(user["family_id"])
        await callback.message.edit_text(f"🗑 <b>Все покупки успешно обнулены!</b> (удалено записей: {count})", parse_mode="HTML")
        await callback.answer("Удалено!")
        # Notify partner
        members = await get_family_members(user["family_id"])
        partner = next((m for m in members if m["id"] != user["id"]), None)
        if partner and partner["id"] > 100:
            await bot.send_message(
                chat_id=partner["id"],
                text=f"🗑 <b>{user['first_name']}</b> обнулил(а) все записи покупок семьи.",
                parse_mode="HTML"
            )

@dp.callback_query(F.data == "cancel_action")
async def cb_cancel_action(callback: types.CallbackQuery):
    await callback.message.edit_text("Действие отменено.")
    await callback.answer()

@dp.message(Command("name"))
async def cmd_rename_user(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Укажите имя, например: <code>/name Евгений</code>", parse_mode="HTML")
        return
    new_name = parts[1].strip()
    await update_user_profile(message.from_user.id, new_name)
    await message.answer(f"✅ Ваше имя изменено на: <b>{new_name}</b>", parse_mode="HTML")

@dp.message(Command("family"))
@dp.message(Command("family_name"))
async def cmd_rename_family(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Укажите фамилию/название, например: <code>/family Семья Солиловых</code>", parse_mode="HTML")
        return
    new_name = parts[1].strip()
    user = await get_user_by_telegram_id(message.from_user.id)
    if user:
        await update_family_name(user["family_id"], new_name)
        await message.answer(f"✅ Название семьи изменено на: <b>{new_name}</b>", parse_mode="HTML")

@dp.message(Command("token"))
async def cmd_set_token(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Укажите желаемый токен, например: <code>/token my_secret_token_123</code>", parse_mode="HTML")
        return
    new_token = parts[1].strip()
    try:
        await update_user_token(message.from_user.id, new_token)
        webhook_url = f"{WEBAPP_URL}/api/shortcuts/add?token={new_token}"
        await message.answer(
            f"✅ <b>Ваш новый токен сохранен!</b>\n\n"
            f"🔑 Токен: <code>{new_token}</code>\n"
            f"🌐 Вебхук для команд: <code>{webhook_url}</code>",
            parse_mode="HTML"
        )
    except ValueError as e:
        await message.answer(f"⚠️ Ошибка: {e}")

@dp.message(F.text == "📲 Команды на iPhone")
@dp.message(Command("shortcuts"))
async def cmd_shortcuts(message: types.Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        user = await create_user_and_family(message.from_user.id, message.from_user.first_name)

    token = user["api_token"]
    webhook_url = f"{WEBAPP_URL}/api/shortcuts/add?token={token}"

    text = (
        f"📲 <b>Настройка Быстрых Команд на iPhone:</b>\n\n"
        f"🔑 <b>Ваш личный токен:</b>\n<code>{token}</code>\n\n"
        f"🌐 <b>Адрес вебхука:</b>\n<code>{webhook_url}</code>\n\n"
        f"Вы можете вводить как траты, так и приход денег (например, <code>+50000 зарплата</code>)!\n"
        f"👉 Подробная инструкция и смена токена доступны в приложении во вкладке «Семья»."
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Открыть инструкцию в Mini App", web_app=WebAppInfo(url=f"{WEBAPP_URL}/"))]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.message(F.text == "🔗 Пригласить супругу")
@dp.message(Command("invite"))
async def cmd_invite(message: types.Message):
    user = await get_user_by_telegram_id(message.from_user.id)
    if not user:
        user = await create_user_and_family(message.from_user.id, message.from_user.first_name)

    family = await get_family_by_id(user["family_id"])
    bot_info = await bot.get_me() if bot else None
    bot_user = bot_info.username if bot_info else "FamilyFinanceBot"
    invite_link = f"https://t.me/{bot_user}?start=join_{family['invite_code']}"

    text = (
        f"💞 <b>Приглашение для супруги:</b>\n\n"
        f"Перешлите ей эту ссылку:\n{invite_link}\n\n"
        f"Или код приглашения: <code>{family['invite_code']}</code>"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.photo)
async def handle_photo_receipt(message: types.Message):
    tg_id = message.from_user.id
    user = await get_user_by_telegram_id(tg_id)
    if not user:
        user = await create_user_and_family(tg_id, message.from_user.first_name)

    await message.answer("🔍 <i>Обрабатываю чек... Распознаю сумму и магазин...</i>", parse_mode="HTML")

    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    filename = f"receipt_{uuid.uuid4().hex}.jpg"
    filepath = UPLOAD_DIR / filename

    await bot.download_file(file_info.file_path, filepath)

    with open(filepath, "rb") as f:
        img_bytes = f.read()

    parsed = await scan_receipt_with_vision(img_bytes, filename)
    receipt_url = f"/uploads/receipts/{filename}"

    expense = await add_expense_record(
        family_id=user["family_id"],
        user_id=user["id"],
        amount=parsed["amount"],
        category_id=parsed["category_id"],
        description=parsed["store_name"],
        expense_date=parsed.get("date"),
        receipt_url=receipt_url,
        receipt_meta=parsed
    )

    amount_str = f"{parsed['amount']:,.0f} ₽".replace(",", " ")
    cat_name = expense.get("category_name", "Продукты")
    cat_icon = expense.get("category_icon", "🛒")

    reply_text = (
        f"🧾 <b>Чек успешно распознан и записан!</b>\n\n"
        f"🏪 <b>Магазин:</b> {parsed['store_name']}\n"
        f"💰 <b>Сумма:</b> <b>{amount_str}</b>\n"
        f"📁 <b>Категория:</b> {cat_icon} {cat_name}\n"
        f"👤 <b>Кто оплатил:</b> {user['first_name']}\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Открыть в приложении", web_app=WebAppInfo(url=f"{WEBAPP_URL}/"))],
        [InlineKeyboardButton(text="❌ Удалить этот чек", callback_data=f"del_exp_{expense['id']}")]
    ])

    await message.answer(reply_text, parse_mode="HTML", reply_markup=kb)

    members = await get_family_members(user["family_id"])
    partner = next((m for m in members if m["id"] != tg_id), None)
    if partner and partner["id"] > 100:
        partner_text = (
            f"🧾 <b>{user['first_name']} добавил(а) чек:</b>\n"
            f"🏪 {parsed['store_name']}\n"
            f"💰 <b>{amount_str}</b> ({cat_icon} {cat_name})"
        )
        try:
            await bot.send_message(chat_id=partner["id"], text=partner_text, parse_mode="HTML")
        except Exception as e:
            print(f"Partner notification error: {e}")

@dp.message(F.text)
async def handle_text_transaction(message: types.Message):
    """Handles text entries for expenses or incomes."""
    text = message.text.strip()
    if text.startswith("/"):
        return

    tg_id = message.from_user.id
    user = await get_user_by_telegram_id(tg_id)
    if not user:
        user = await create_user_and_family(tg_id, message.from_user.first_name)

    lower = text.lower()
    is_income = text.startswith("+") or any(w in lower for w in ["доход", "зарплат", "преми", "аванс", "подработк", "кэшбэк", "приход"])

    parsed = await parse_expense_text(text.lstrip("+"))
    if not parsed.get("amount") or parsed["amount"] <= 0:
        await message.answer(
            "💡 Чтобы записать трату, укажите сумму и покупку.\n"
            "Например: <code>1500 продукты</code> или <code>Бензин 2500</code>\n"
            "Для записи дохода напишите: <code>+50000 зарплата</code>",
            parse_mode="HTML"
        )
        return

    amount_str = f"{parsed['amount']:,.0f} ₽".replace(",", " ")

    if is_income:
        source = "Зарплата"
        if "преми" in lower:
            source = "Премия"
        elif "аванс" in lower:
            source = "Аванс"
        elif "подработк" in lower:
            source = "Подработка"
        elif "кэшбэк" in lower:
            source = "Кэшбэк/Проценты"
        elif "подарок" in lower:
            source = "Подарок"

        income = await add_income_record(
            family_id=user["family_id"],
            user_id=user["id"],
            amount=parsed["amount"],
            source=source,
            description=parsed["description"]
        )

        reply_text = (
            f"💵 <b>Приход денег записан!</b>\n\n"
            f"💰 <b>+{amount_str}</b>\n"
            f"📁 <b>Источник:</b> {source}\n"
            f"👤 <b>Получатель:</b> {user['first_name']}"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Открыть трекер", web_app=WebAppInfo(url=f"{WEBAPP_URL}/"))],
            [InlineKeyboardButton(text="❌ Удалить этот доход", callback_data=f"del_inc_{income['id']}")]
        ])
        await message.answer(reply_text, parse_mode="HTML", reply_markup=kb)

        # Notify partner
        members = await get_family_members(user["family_id"])
        partner = next((m for m in members if m["id"] != tg_id), None)
        if partner and partner["id"] > 100:
            partner_text = (
                f"💵 <b>{user['first_name']} записал(а) доход:</b>\n"
                f"💰 <b>+{amount_str}</b> ({source})"
            )
            try:
                await bot.send_message(chat_id=partner["id"], text=partner_text, parse_mode="HTML")
            except Exception as e:
                print(f"Partner notification error: {e}")

    else:
        expense = await add_expense_record(
            family_id=user["family_id"],
            user_id=user["id"],
            amount=parsed["amount"],
            category_id=parsed["category_id"],
            description=parsed["description"]
        )

        cat_name = expense.get("category_name", "Расход")
        cat_icon = expense.get("category_icon", "💳")

        reply_text = (
            f"✅ <b>Расход записан!</b>\n\n"
            f"💰 <b>{amount_str}</b>\n"
            f"📁 <b>Категория:</b> {cat_icon} {cat_name}\n"
            f"📝 <b>Описание:</b> {parsed['description']}\n"
            f"👤 <b>Кто оплатил:</b> {user['first_name']}"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Открыть трекер", web_app=WebAppInfo(url=f"{WEBAPP_URL}/"))],
            [InlineKeyboardButton(text="❌ Удалить расход", callback_data=f"del_exp_{expense['id']}")]
        ])
        await message.answer(reply_text, parse_mode="HTML", reply_markup=kb)

        members = await get_family_members(user["family_id"])
        partner = next((m for m in members if m["id"] != tg_id), None)
        if partner and partner["id"] > 100:
            partner_text = (
                f"🔔 <b>{user['first_name']} записал(а) расход:</b>\n"
                f"💰 <b>{amount_str}</b> — {cat_icon} {cat_name} ({parsed['description']})"
            )
            try:
                await bot.send_message(chat_id=partner["id"], text=partner_text, parse_mode="HTML")
            except Exception as e:
                print(f"Partner notification error: {e}")

@dp.callback_query(F.data.startswith("del_exp_"))
async def cb_delete_expense(callback: types.CallbackQuery):
    exp_id = int(callback.data.replace("del_exp_", ""))
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user:
        await delete_expense_record(exp_id, user["family_id"])
        await callback.message.edit_text("🗑 <b>Расход удален.</b>", parse_mode="HTML")
    await callback.answer("Удалено")

@dp.callback_query(F.data.startswith("del_inc_"))
async def cb_delete_income(callback: types.CallbackQuery):
    inc_id = int(callback.data.replace("del_inc_", ""))
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user:
        from backend.database import delete_income_record
        await delete_income_record(inc_id, user["family_id"])
        await callback.message.edit_text("🗑 <b>Запись дохода удалена.</b>", parse_mode="HTML")
    await callback.answer("Удалено")

@dp.callback_query(F.data == "show_shortcuts")
async def cb_show_shortcuts(callback: types.CallbackQuery):
    await callback.answer()
    await cmd_shortcuts(callback.message)

async def start_bot():
    global bot
    if not BOT_TOKEN:
        print("⚠️ BOT_TOKEN is not configured in .env. Telegram Bot polling disabled, but WebApp and Shortcuts API are running!")
        return None

    bot = Bot(token=BOT_TOKEN)
    set_bot_instance(bot)
    print("🤖 Telegram Bot started in background polling mode.")
    return bot, dp
