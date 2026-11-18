import aiosqlite
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, date
from pathlib import Path
from backend.config import DB_PATH

DEFAULT_CATEGORIES = [
    {"id": "groceries", "name": "Продукты", "icon": "🛒", "color": "#34C759"},
    {"id": "child", "name": "Ребенок", "icon": "👶", "color": "#FF9500"},
    {"id": "car", "name": "Машина", "icon": "🚗", "color": "#007AFF"},
    {"id": "subs", "name": "Подписки", "icon": "📱", "color": "#AF52DE"},
    {"id": "cafes", "name": "Кафе и еда", "icon": "☕️", "color": "#FF2D55"},
    {"id": "home", "name": "Дом и быт", "icon": "🏠", "color": "#5856D6"},
    {"id": "health", "name": "Здоровье", "icon": "💊", "color": "#30B0C7"},
    {"id": "fun", "name": "Развлечения", "icon": "🎁", "color": "#FFCC00"},
    {"id": "other", "name": "Прочее", "icon": "📦", "color": "#8E8E93"},
]

DEFAULT_INCOME_SOURCES = [
    {"id": "salary", "name": "Зарплата", "icon": "💰"},
    {"id": "advance", "name": "Аванс", "icon": "💵"},
    {"id": "bonus", "name": "Премия", "icon": "🎯"},
    {"id": "sidejob", "name": "Подработка", "icon": "💼"},
    {"id": "cashback", "name": "Кэшбэк/Проценты", "icon": "💳"},
    {"id": "gift", "name": "Подарок", "icon": "🎁"},
    {"id": "other_inc", "name": "Другой доход", "icon": "📦"},
]

@asynccontextmanager
async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.execute("PRAGMA journal_mode = WAL;")
        yield db

async def init_db():
    async with get_db() as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS families (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            invite_code TEXT UNIQUE NOT NULL,
            monthly_budget REAL DEFAULT 150000.0,
            currency TEXT DEFAULT '₽',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            family_id INTEGER REFERENCES families(id) ON DELETE CASCADE,
            first_name TEXT NOT NULL,
            username TEXT,
            role TEXT DEFAULT 'Супруг(а)',
            avatar_color TEXT DEFAULT '#3a8bf7',
            api_token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            icon TEXT NOT NULL,
            color TEXT NOT NULL
        );
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            amount REAL NOT NULL,
            category_id TEXT NOT NULL REFERENCES categories(id),
            description TEXT,
            receipt_url TEXT,
            receipt_meta TEXT,
            expense_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS incomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            amount REAL NOT NULL,
            source TEXT NOT NULL DEFAULT 'Зарплата',
            description TEXT,
            income_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Insert default categories
        for cat in DEFAULT_CATEGORIES:
            await db.execute(
                "INSERT OR IGNORE INTO categories (id, name, icon, color) VALUES (?, ?, ?, ?)",
                (cat["id"], cat["name"], cat["icon"], cat["color"])
            )

        # Check if default family exists; if not, create seed data
        cursor = await db.execute("SELECT id FROM families LIMIT 1")
        row = await cursor.fetchone()
        today = date.today().strftime("%Y-%m-%d")

        if not row:
            invite_code = secrets.token_hex(4).upper()
            cursor = await db.execute(
                "INSERT INTO families (name, invite_code, monthly_budget, currency) VALUES (?, ?, ?, ?)",
                ("Семья Солиловых", invite_code, 150000.0, "₽")
            )
            family_id = cursor.lastrowid

            # Create default users: Евгений and Супруга
            await db.execute(
                """
                INSERT INTO users (id, family_id, first_name, username, role, avatar_color, api_token)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (1, family_id, "Евгений", "evgeniy", "Евгений", "#3a8bf7", "tok_evgeniy_12345")
            )
            await db.execute(
                """
                INSERT INTO users (id, family_id, first_name, username, role, avatar_color, api_token)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (2, family_id, "Супруга", "wife", "Супруга", "#ff5a8a", "tok_wife_67890")
            )

            # Insert sample realistic expenses for current month
            sample_expenses = [
                (family_id, 1, 3450.0, "groceries", "Супермаркет Перекресток", today, None),
                (family_id, 2, 1890.0, "groceries", "ВкусВилл свежие ягоды и сыр", today, None),
                (family_id, 1, 2600.0, "car", "Бензин АИ-95 Лукойл", today, None),
                (family_id, 2, 4500.0, "child", "Детская зимняя обувь", today, None),
                (family_id, 1, 299.0, "subs", "Яндекс Плюс Мульти", today, None),
                (family_id, 2, 1200.0, "cafes", "Кофе и десерты в Surf Coffee", today, None),
                (family_id, 1, 1450.0, "health", "Витамины в Аптеке 36.6", today, None),
                (family_id, 2, 3800.0, "home", "Текстиль и посуда для дома", today, None),
                (family_id, 1, 5200.0, "car", "Замена масла и фильтров", today, None),
                (family_id, 2, 6500.0, "child", "Развивающие занятия и бассейн", today, None),
                (family_id, 1, 2100.0, "fun", "Билеты в кино и попкорн", today, None),
            ]
            for exp in sample_expenses:
                await db.execute(
                    """
                    INSERT INTO expenses (family_id, user_id, amount, category_id, description, expense_date, receipt_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    exp
                )

            # Insert sample realistic incomes for current month
            sample_incomes = [
                (family_id, 1, 130000.0, "Зарплата", "Основная зарплата", today),
                (family_id, 2, 95000.0, "Зарплата", "Основная зарплата", today),
                (family_id, 1, 15000.0, "Премия", "Квартальная премия", today),
                (family_id, 2, 4500.0, "Кэшбэк/Проценты", "Кэшбэк по карте", today),
            ]
            for inc in sample_incomes:
                await db.execute(
                    """
                    INSERT INTO incomes (family_id, user_id, amount, source, description, income_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    inc
                )
        else:
            # Check if incomes table has seed data
            cursor = await db.execute("SELECT id FROM incomes LIMIT 1")
            inc_row = await cursor.fetchone()
            if not inc_row:
                family_id = row["id"]
                sample_incomes = [
                    (family_id, 1, 130000.0, "Зарплата", "Основная зарплата", today),
                    (family_id, 2, 95000.0, "Зарплата", "Основная зарплата", today),
                    (family_id, 1, 15000.0, "Премия", "Квартальная премия", today),
                    (family_id, 2, 4500.0, "Кэшбэк/Проценты", "Кэшбэк по карте", today),
                ]
                for inc in sample_incomes:
                    await db.execute(
                        """
                        INSERT INTO incomes (family_id, user_id, amount, source, description, income_date)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        inc
                    )

        await db.commit()

async def get_user_by_token(token: str):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM users WHERE api_token = ?", (token,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_user_by_telegram_id(tg_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (tg_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_family_by_id(family_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM families WHERE id = ?", (family_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_family_members(family_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM users WHERE family_id = ? ORDER BY id ASC", (family_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def update_family_name(family_id: int, name: str):
    async with get_db() as db:
        await db.execute("UPDATE families SET name = ? WHERE id = ?", (name.strip(), family_id))
        await db.commit()
        return await get_family_by_id(family_id)

async def update_user_profile(user_id: int, first_name: str, role: str = None):
    async with get_db() as db:
        if role:
            await db.execute("UPDATE users SET first_name = ?, role = ? WHERE id = ?", (first_name.strip(), role.strip(), user_id))
        else:
            await db.execute("UPDATE users SET first_name = ? WHERE id = ?", (first_name.strip(), user_id))
        await db.commit()
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def update_user_token(user_id: int, new_token: str):
    clean_token = new_token.strip()
    if not clean_token:
        raise ValueError("Токен не может быть пустым.")
    async with get_db() as db:
        # Check if already in use by another user
        cursor = await db.execute("SELECT id FROM users WHERE api_token = ? AND id != ?", (clean_token, user_id))
        existing = await cursor.fetchone()
        if existing:
            raise ValueError("Этот токен уже используется другим аккаунтом. Выберите другой токен.")
        await db.execute("UPDATE users SET api_token = ? WHERE id = ?", (clean_token, user_id))
        await db.commit()
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def create_user_and_family(tg_id: int, first_name: str, username: str = None, role: str = "Супруг"):
    async with get_db() as db:
        invite_code = secrets.token_hex(4).upper()
        cursor = await db.execute(
            "INSERT INTO families (name, invite_code) VALUES (?, ?)",
            (f"Семья {first_name}", invite_code)
        )
        family_id = cursor.lastrowid
        token = "tok_" + secrets.token_hex(8)
        color = "#3a8bf7"
        await db.execute(
            """
            INSERT INTO users (id, family_id, first_name, username, role, avatar_color, api_token)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tg_id, family_id, first_name, username, role, color, token)
        )
        await db.commit()
        return await get_user_by_telegram_id(tg_id)

async def join_family_by_code(tg_id: int, invite_code: str, first_name: str, username: str = None, role: str = "Супруга"):
    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM families WHERE invite_code = ?", (invite_code.strip().upper(),))
        row = await cursor.fetchone()
        if not row:
            return None
        family_id = row["id"]

        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (tg_id,))
        user_row = await cursor.fetchone()
        token = "tok_" + secrets.token_hex(8)
        color = "#ff5a8a" if role == "Супруга" else "#3a8bf7"
        if user_row:
            await db.execute("UPDATE users SET family_id = ?, role = ? WHERE id = ?", (family_id, role, tg_id))
        else:
            await db.execute(
                """
                INSERT INTO users (id, family_id, first_name, username, role, avatar_color, api_token)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (tg_id, family_id, first_name, username, role, color, token)
            )
        await db.commit()
        return await get_user_by_telegram_id(tg_id)

# ================= EXPENSES =================
async def add_expense_record(
    family_id: int,
    user_id: int,
    amount: float,
    category_id: str,
    description: str,
    expense_date: str = None,
    receipt_url: str = None,
    receipt_meta: dict = None
):
    if not expense_date:
        expense_date = date.today().strftime("%Y-%m-%d")

    async with get_db() as db:
        meta_json = json.dumps(receipt_meta, ensure_ascii=False) if receipt_meta else None
        cursor = await db.execute(
            """
            INSERT INTO expenses (family_id, user_id, amount, category_id, description, receipt_url, receipt_meta, expense_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (family_id, user_id, amount, category_id, description, receipt_url, meta_json, expense_date)
        )
        await db.commit()
        expense_id = cursor.lastrowid

        cursor = await db.execute(
            """
            SELECT e.*, u.first_name, u.role, u.avatar_color, c.name as category_name, c.icon as category_icon, c.color as category_color
            FROM expenses e
            JOIN users u ON e.user_id = u.id
            JOIN categories c ON e.category_id = c.id
            WHERE e.id = ?
            """,
            (expense_id,)
        )
        row = await cursor.fetchone()
        return dict(row)

async def get_expenses_list(family_id: int, month_prefix: str = None, user_id: int = None, category_id: str = None):
    query = """
        SELECT e.*, u.first_name, u.role, u.avatar_color, c.name as category_name, c.icon as category_icon, c.color as category_color
        FROM expenses e
        JOIN users u ON e.user_id = u.id
        JOIN categories c ON e.category_id = c.id
        WHERE e.family_id = ?
    """
    params = [family_id]

    if month_prefix:
        query += " AND e.expense_date LIKE ?"
        params.append(f"{month_prefix}%")

    if user_id:
        query += " AND e.user_id = ?"
        params.append(user_id)

    if category_id and category_id != "all":
        query += " AND e.category_id = ?"
        params.append(category_id)

    query += " ORDER BY e.expense_date DESC, e.id DESC"

    async with get_db() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def delete_expense_record(expense_id: int, family_id: int):
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM expenses WHERE id = ? AND family_id = ?", (expense_id, family_id))
        await db.commit()
        return cursor.rowcount > 0

async def delete_all_expenses(family_id: int):
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM expenses WHERE family_id = ?", (family_id,))
        await db.commit()
        return cursor.rowcount

# ================= INCOMES (ПРИХОД ДЕНЕГ) =================
async def add_income_record(
    family_id: int,
    user_id: int,
    amount: float,
    source: str = "Зарплата",
    description: str = None,
    income_date: str = None
):
    if not income_date:
        income_date = date.today().strftime("%Y-%m-%d")

    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO incomes (family_id, user_id, amount, source, description, income_date)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (family_id, user_id, amount, source, description, income_date)
        )
        await db.commit()
        income_id = cursor.lastrowid

        cursor = await db.execute(
            """
            SELECT i.*, u.first_name, u.role, u.avatar_color
            FROM incomes i
            JOIN users u ON i.user_id = u.id
            WHERE i.id = ?
            """,
            (income_id,)
        )
        row = await cursor.fetchone()
        return dict(row)

async def get_incomes_list(family_id: int, month_prefix: str = None, user_id: int = None):
    query = """
        SELECT i.*, u.first_name, u.role, u.avatar_color
        FROM incomes i
        JOIN users u ON i.user_id = u.id
        WHERE i.family_id = ?
    """
    params = [family_id]

    if month_prefix:
        query += " AND i.income_date LIKE ?"
        params.append(f"{month_prefix}%")

    if user_id:
        query += " AND i.user_id = ?"
        params.append(user_id)

    query += " ORDER BY i.income_date DESC, i.id DESC"

    async with get_db() as db:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

async def delete_income_record(income_id: int, family_id: int):
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM incomes WHERE id = ? AND family_id = ?", (income_id, family_id))
        await db.commit()
        return cursor.rowcount > 0

async def delete_all_incomes(family_id: int):
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM incomes WHERE family_id = ?", (family_id,))
        await db.commit()
        return cursor.rowcount

# ================= MONTHLY ANALYTICS =================
async def get_family_monthly_analytics(family_id: int, month_prefix: str = None):
    if not month_prefix:
        month_prefix = date.today().strftime("%Y-%m")

    async with get_db() as db:
        # Total spent (expenses)
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE family_id = ? AND expense_date LIKE ?",
            (family_id, f"{month_prefix}%")
        )
        total_row = await cursor.fetchone()
        total_spent = total_row["total"]

        # Total income (приход денег)
        cursor = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) as total_inc FROM incomes WHERE family_id = ? AND income_date LIKE ?",
            (family_id, f"{month_prefix}%")
        )
        inc_row = await cursor.fetchone()
        total_income = inc_row["total_inc"]

        # Net savings / balance = income - expenses
        net_balance = total_income - total_spent

        # Family budget
        cursor = await db.execute("SELECT name, monthly_budget, currency FROM families WHERE id = ?", (family_id,))
        fam_row = await cursor.fetchone()
        budget = fam_row["monthly_budget"] if fam_row else 150000.0
        currency = fam_row["currency"] if fam_row else "₽"
        family_name = fam_row["name"] if fam_row else "Семья"

        # Expenses By User
        cursor = await db.execute(
            """
            SELECT u.id, u.first_name, u.role, u.avatar_color, COALESCE(SUM(e.amount), 0) as total_user
            FROM users u
            LEFT JOIN expenses e ON e.user_id = u.id AND e.expense_date LIKE ?
            WHERE u.family_id = ?
            GROUP BY u.id
            ORDER BY u.id ASC
            """,
            (f"{month_prefix}%", family_id)
        )
        users_rows = await cursor.fetchall()
        users_breakdown = [dict(r) for r in users_rows]

        # Incomes By User
        cursor = await db.execute(
            """
            SELECT u.id, u.first_name, u.role, u.avatar_color, COALESCE(SUM(i.amount), 0) as total_user_income
            FROM users u
            LEFT JOIN incomes i ON i.user_id = u.id AND i.income_date LIKE ?
            WHERE u.family_id = ?
            GROUP BY u.id
            ORDER BY u.id ASC
            """,
            (f"{month_prefix}%", family_id)
        )
        inc_user_rows = await cursor.fetchall()
        income_users_breakdown = [dict(r) for r in inc_user_rows]

        # Incomes By Source
        cursor = await db.execute(
            """
            SELECT source, COALESCE(SUM(amount), 0) as total_source, COUNT(id) as count_source
            FROM incomes
            WHERE family_id = ? AND income_date LIKE ?
            GROUP BY source
            ORDER BY total_source DESC
            """,
            (family_id, f"{month_prefix}%")
        )
        source_rows = await cursor.fetchall()
        sources_breakdown = []
        for r in source_rows:
            pct = round((r["total_source"] / total_income * 100), 1) if total_income > 0 else 0
            sources_breakdown.append({
                "source": r["source"],
                "total": r["total_source"],
                "count": r["count_source"],
                "percentage": pct
            })

        # Calculate 50/50 split settlement for expenses
        split_settlement = None
        if len(users_breakdown) >= 2:
            u1, u2 = users_breakdown[0], users_breakdown[1]
            diff = abs(u1["total_user"] - u2["total_user"]) / 2.0
            if u1["total_user"] > u2["total_user"]:
                split_settlement = {
                    "payer": u2["first_name"],
                    "receiver": u1["first_name"],
                    "amount": round(diff, 2),
                    "text": f"{u2['first_name']} переводит {u1['first_name']} {round(diff):,} {currency}".replace(",", " ")
                }
            elif u2["total_user"] > u1["total_user"]:
                split_settlement = {
                    "payer": u1["first_name"],
                    "receiver": u2["first_name"],
                    "amount": round(diff, 2),
                    "text": f"{u1['first_name']} переводит {u2['first_name']} {round(diff):,} {currency}".replace(",", " ")
                }
            else:
                split_settlement = {
                    "payer": None,
                    "receiver": None,
                    "amount": 0,
                    "text": "Расходы равны 50/50!"
                }

        # By Category
        cursor = await db.execute(
            """
            SELECT c.id, c.name, c.icon, c.color, COALESCE(SUM(e.amount), 0) as total_cat, COUNT(e.id) as count_cat
            FROM categories c
            JOIN expenses e ON e.category_id = c.id
            WHERE e.family_id = ? AND e.expense_date LIKE ?
            GROUP BY c.id
            HAVING total_cat > 0
            ORDER BY total_cat DESC
            """,
            (family_id, f"{month_prefix}%")
        )
        cat_rows = await cursor.fetchall()
        categories_breakdown = []
        for r in cat_rows:
            pct = round((r["total_cat"] / total_spent * 100), 1) if total_spent > 0 else 0
            categories_breakdown.append({
                "id": r["id"],
                "name": r["name"],
                "icon": r["icon"],
                "color": r["color"],
                "total": r["total_cat"],
                "count": r["count_cat"],
                "percentage": pct
            })

        # By Day (dynamics for chart)
        cursor = await db.execute(
            """
            SELECT expense_date, SUM(amount) as daily_total
            FROM expenses
            WHERE family_id = ? AND expense_date LIKE ?
            GROUP BY expense_date
            ORDER BY expense_date ASC
            """,
            (family_id, f"{month_prefix}%")
        )
        daily_rows = await cursor.fetchall()
        daily_dynamics = [{"date": r["expense_date"], "total": r["daily_total"]} for r in daily_rows]

        return {
            "month": month_prefix,
            "family_name": family_name,
            "total_spent": total_spent,
            "total_income": total_income,
            "net_balance": net_balance,
            "monthly_budget": budget,
            "currency": currency,
            "budget_spent_pct": round((total_spent / budget * 100), 1) if budget > 0 else 0,
            "savings_pct": round((net_balance / total_income * 100), 1) if total_income > 0 else 0,
            "users": users_breakdown,
            "income_users": income_users_breakdown,
            "income_sources": sources_breakdown,
            "split": split_settlement,
            "categories": categories_breakdown,
            "dynamics": daily_dynamics
        }
