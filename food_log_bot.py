import asyncio
import logging
import asyncpg
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import os
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "food_log_bot"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "your_password"),
    "port": os.getenv("DB_PORT", "5432")
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class LogFoodForm(StatesGroup):
    food_name = State()
    weight = State()

class AddFoodForm(StatesGroup):
    food_name = State()
    calories_per_gram = State()

class UpdateFoodForm(StatesGroup):
    food_id = State()
    field = State()
    value = State()

class SetGoalForm(StatesGroup):
    calorie_goal = State()

async def init_db():
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS Users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                calorie_goal FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS Foods (
                food_id SERIAL PRIMARY KEY,
                food_name TEXT NOT NULL,
                calories_per_gram FLOAT NOT NULL,
                user_id BIGINT REFERENCES Users(user_id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS DailyLog (
                log_id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES Users(user_id),
                food_id INTEGER REFERENCES Foods(food_id),
                weight_grams FLOAT NOT NULL,
                calories FLOAT NOT NULL,
                log_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await conn.execute("""
            DO $$ 
            BEGIN
                -- Add user_id column if not exists
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name = 'foods' AND column_name = 'user_id'
                ) THEN
                    ALTER TABLE Foods ADD COLUMN user_id BIGINT REFERENCES Users(user_id);
                END IF;
                -- Drop old unique constraint on food_name if exists
                IF EXISTS (
                    SELECT 1 
                    FROM information_schema.constraint_table_usage 
                    WHERE table_name = 'foods' AND constraint_name = 'foods_food_name_key'
                ) THEN
                    ALTER TABLE Foods DROP CONSTRAINT foods_food_name_key;
                END IF;
                -- Add new unique constraint on (food_name, user_id) if not exists
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.constraint_table_usage 
                    WHERE table_name = 'foods' AND constraint_name = 'unique_food_user'
                ) THEN
                    ALTER TABLE Foods ADD CONSTRAINT unique_food_user UNIQUE (food_name, user_id);
                END IF;
            END $$;
        """)

        await conn.execute("""
            INSERT INTO Foods (food_name, calories_per_gram, user_id)
            VALUES
                ('Apple', 0.52, NULL),
                ('Chicken Breast', 1.65, NULL),
                ('Rice', 1.30, NULL),
                ('Banana', 0.89, NULL),
                ('Salmon', 2.08, NULL),
                ('Broccoli', 0.35, NULL),
                ('Bread', 2.65, NULL)
            ON CONFLICT ON CONSTRAINT unique_food_user DO NOTHING;
        """)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    finally:
        await conn.close()

async def get_main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍽️ Log Food"), KeyboardButton(text="➕ Add Food")],
            [KeyboardButton(text="📖 My Foods"), KeyboardButton(text="📅 Daily Summary")],
            [KeyboardButton(text="📊 Weekly Summary"), KeyboardButton(text="🎯 Set Calorie Goal")]
        ],
        resize_keyboard=True
    )
    return keyboard

async def get_food_keyboard(user_id: int):
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        foods = await conn.fetch("""
            SELECT food_name
            FROM Foods
            WHERE user_id = $1 OR user_id IS NULL
            ORDER BY food_name
        """, user_id)
        keyboard_buttons = [[KeyboardButton(text=food['food_name'])] for food in foods]
        keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
        return keyboard
    finally:
        await conn.close()

async def register_user(user: types.User):
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        await conn.execute("""
            INSERT INTO Users (user_id, username, first_name, last_name, created_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id) DO NOTHING
        """, user.id, user.username, user.first_name, user.last_name, datetime.now())
    finally:
        await conn.close()

async def log_food(user_id: int, food_name: str, weight: float):
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        food = await conn.fetchrow("""
            SELECT food_id, calories_per_gram
            FROM Foods
            WHERE food_name = $1 AND (user_id = $2 OR user_id IS NULL)
        """, food_name, user_id)
        if not food:
            return None
        calories = food['calories_per_gram'] * weight
        await conn.execute("""
            INSERT INTO DailyLog (user_id, food_id, weight_grams, calories, log_date)
            VALUES ($1, $2, $3, $4, $5)
        """, user_id, food['food_id'], weight, calories, datetime.now())
        return calories
    finally:
        await conn.close()

async def get_daily_summary(user_id: int, date: datetime):
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        logs = await conn.fetch("""
            SELECT f.food_name, dl.weight_grams, dl.calories, dl.log_date
            FROM DailyLog dl
            JOIN Foods f ON dl.food_id = f.food_id
            WHERE dl.user_id = $1
            AND DATE(dl.log_date) = DATE($2)
            ORDER BY dl.log_date
        """, user_id, date)
        total_calories = sum(log['calories'] for log in logs)
        calorie_goal = await conn.fetchval("SELECT calorie_goal FROM Users WHERE user_id = $1", user_id)
        return logs, total_calories, calorie_goal
    finally:
        await conn.close()

async def get_weekly_summary(user_id: int, end_date: datetime):
    start_date = end_date - timedelta(days=6)
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        logs = await conn.fetch("""
            SELECT DATE(dl.log_date) as log_day, SUM(dl.calories) as daily_calories
            FROM DailyLog dl
            WHERE dl.user_id = $1
            AND dl.log_date >= $2
            AND dl.log_date <= $3
            GROUP BY DATE(dl.log_date)
            ORDER BY DATE(dl.log_date)
        """, user_id, start_date, end_date)
        total_calories = sum(log['daily_calories'] for log in logs)
        calorie_goal = await conn.fetchval("SELECT calorie_goal FROM Users WHERE user_id = $1", user_id)
        return logs, total_calories, calorie_goal
    finally:
        await conn.close()

async def get_user_foods(user_id: int):
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        foods = await conn.fetch("""
            SELECT food_id, food_name, calories_per_gram
            FROM Foods
            WHERE user_id = $1
            ORDER BY food_name
        """, user_id)
        return foods
    finally:
        await conn.close()

async def get_user_stats(user_id: int):
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        stats = await conn.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM Foods WHERE user_id = $1) as foods_added,
                (SELECT COUNT(*) FROM DailyLog WHERE user_id = $1) as logs_created,
                (SELECT AVG(SUM(dl.calories)) FROM DailyLog dl 
                 WHERE dl.user_id = $1 
                 GROUP BY DATE(dl.log_date)) as avg_daily_calories
        """, user_id)
        return stats
    finally:
        await conn.close()

@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    await state.clear()
    await register_user(message.from_user)
    keyboard = await get_main_menu()
    await message.answer(
        "Welcome to the Enhanced Food Log Bot! 🍎\n"
        "Track your meals, add custom foods, and monitor your calorie goals. What would you like to do?",
        reply_markup=keyboard
    )

@dp.message(lambda message: message.text == "🍽️ Log Food")
async def log_food_start(message: types.Message, state: FSMContext):
    await state.clear()
    keyboard = await get_food_keyboard(message.from_user.id)
    await message.answer(
        "Select a food item to log:",
        reply_markup=keyboard
    )
    await state.set_state(LogFoodForm.food_name)

@dp.message(lambda message: message.text == "➕ Add Food")
async def add_food_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Enter the food name:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(AddFoodForm.food_name)

@dp.message(lambda message: message.text == "📖 My Foods")
async def my_foods(message: types.Message, state: FSMContext):
    await state.clear()
    foods = await get_user_foods(message.from_user.id)
    if not foods:
        await message.answer("You haven't added any custom foods yet. Use 'Add Food' to start!", reply_markup=await get_main_menu())
        return

    response = "Your custom foods:\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for food in foods:
        response += f"🍽️ {food['food_name']}: {food['calories_per_gram']:.2f} kcal/g\n"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"Update {food['food_name']}", callback_data=f"update_{food['food_id']}"),
            InlineKeyboardButton(text=f"Delete {food['food_name']}", callback_data=f"delete_{food['food_id']}")
        ])
    
    await message.answer(response, parse_mode="Markdown", reply_markup=keyboard)
    await message.answer("Back to main menu:", reply_markup=await get_main_menu())

@dp.message(lambda message: message.text == "📅 Daily Summary")
async def daily_summary(message: types.Message, state: FSMContext):
    await state.clear()
    logs, total_calories, calorie_goal = await get_daily_summary(message.from_user.id, datetime.now())
    if not logs:
        await message.answer("No food logged for today. Start logging with 'Log Food'!", reply_markup=await get_main_menu())
        return

    response = f"Daily Summary ({datetime.now().strftime('%Y-%m-%d')}):\n\n"
    for log in logs:
        response += f"🍽️ {log['food_name']}: {log['weight_grams']}g ({log['calories']:.1f} kcal)\n"
    response += f"\nTotal Calories: {total_calories:.1f} kcal"
    if calorie_goal:
        response += f"\nCalorie Goal: {calorie_goal:.1f} kcal ({(total_calories/calorie_goal*100):.1f}% of goal)"
    await message.answer(response, reply_markup=await get_main_menu())

@dp.message(lambda message: message.text == "📊 Weekly Summary")
async def weekly_summary(message: types.Message, state: FSMContext):
    await state.clear()
    logs, total_calories, calorie_goal = await get_weekly_summary(message.from_user.id, datetime.now())
    if not logs:
        await message.answer("No food logged for this week. Start logging with 'Log Food'!", reply_markup=await get_main_menu())
        return

    response = f"Weekly Summary (Last 7 Days):\n\n"
    for log in logs:
        response += f"📅 {log['log_day'].strftime('%Y-%m-%d')}: {log['daily_calories']:.1f} kcal\n"
    response += f"\nTotal Weekly Calories: {total_calories:.1f} kcal"
    if calorie_goal:
        response += f"\nDaily Calorie Goal: {calorie_goal:.1f} kcal (Average: {(total_calories/7):.1f} kcal/day)"
    await message.answer(response, reply_markup=await get_main_menu())

@dp.message(lambda message: message.text == "🎯 Set Calorie Goal")
async def set_calorie_goal_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Enter your daily calorie goal (e.g., 2000):", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(SetGoalForm.calorie_goal)

@dp.message(LogFoodForm.food_name)
async def process_food_name(message: types.Message, state: FSMContext):
    food_name = message.text
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        food_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM Foods WHERE food_name = $1 AND (user_id = $2 OR user_id IS NULL))",
            food_name, message.from_user.id
        )
        if not food_exists:
            await message.answer(
                "Please select a valid food from the keyboard below:",
                reply_markup=await get_food_keyboard(message.from_user.id)
            )
            return
        await state.update_data(food_name=food_name)
        await message.answer("Enter the weight in grams (e.g., 100):", reply_markup=types.ReplyKeyboardRemove())
        await state.set_state(LogFoodForm.weight)
    finally:
        await conn.close()

@dp.message(LogFoodForm.weight)
async def process_weight(message: types.Message, state: FSMContext):
    try:
        weight = float(message.text)
        if weight <= 0:
            await message.answer("Please enter a positive weight in grams:")
            return
        data = await state.get_data()
        calories = await log_food(message.from_user.id, data['food_name'], weight)
        if calories is None:
            await message.answer("Food not found. Please try again.", reply_markup=await get_main_menu())
            await state.clear()
            return
        await message.answer(
            f"Logged {data['food_name']}: {weight}g ({calories:.1f} kcal)",
            reply_markup=await get_main_menu()
        )
        await state.clear()
    except ValueError:
        await message.answer("Please enter a valid number for the weight:")

@dp.message(AddFoodForm.food_name)
async def process_food_name_add(message: types.Message, state: FSMContext):
    await state.update_data(food_name=message.text)
    await message.answer("Enter the calories per gram (e.g., 0.52 for apples):")
    await state.set_state(AddFoodForm.calories_per_gram)

@dp.message(AddFoodForm.calories_per_gram)
async def process_calories_per_gram(message: types.Message, state: FSMContext):
    try:
        calories_per_gram = float(message.text)
        if calories_per_gram <= 0:
            await message.answer("Please enter a positive value for calories per gram:")
            return
        data = await state.get_data()
        conn = await asyncpg.connect(**DB_CONFIG)
        try:
            await conn.execute("""
                INSERT INTO Foods (food_name, calories_per_gram, user_id)
                VALUES ($1, $2, $3)
            """, data['food_name'], calories_per_gram, message.from_user.id)
            await message.answer("Food added successfully!", reply_markup=await get_main_menu())
            await state.clear()
        except asyncpg.UniqueViolationError:
            await message.answer("This food name already exists for you. Try a different name.", reply_markup=await get_main_menu())
            await state.clear()
        finally:
            await conn.close()
    except ValueError:
        await message.answer("Please enter a valid number for calories per gram:")

@dp.message(SetGoalForm.calorie_goal)
async def process_calorie_goal(message: types.Message, state: FSMContext):
    try:
        calorie_goal = float(message.text)
        if calorie_goal <= 0:
            await message.answer("Please enter a positive calorie goal:")
            return
        conn = await asyncpg.connect(**DB_CONFIG)
        try:
            await conn.execute("""
                UPDATE Users SET calorie_goal = $1 WHERE user_id = $2
            """, calorie_goal, message.from_user.id)
            await message.answer(f"Daily calorie goal set to {calorie_goal:.1f} kcal!", reply_markup=await get_main_menu())
            await state.clear()
        finally:
            await conn.close()
    except ValueError:
        await message.answer("Please enter a valid number for the calorie goal:")

@dp.callback_query(lambda c: c.data.startswith("update_"))
async def update_food_start(callback: types.CallbackQuery, state: FSMContext):
    food_id = int(callback.data.split("_")[1])
    await state.update_data(food_id=food_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Food Name", callback_data="field_food_name")],
        [InlineKeyboardButton(text="Calories per Gram", callback_data="field_calories_per_gram")]
    ])
    await callback.message.answer("Which field would you like to update?", reply_markup=keyboard)
    await state.set_state(UpdateFoodForm.field)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("field_"))
async def process_update_field(callback: types.CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[1]
    await state.update_data(field=field)
    await callback.message.answer(f"Enter the new value for {field.replace('_', ' ')}:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(UpdateFoodForm.value)
    await callback.answer()

@dp.message(UpdateFoodForm.value)
async def process_update_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data['field']
    food_id = data['food_id']
    value = message.text
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        if field == "calories_per_gram":
            value = float(value)
            if value <= 0:
                await message.answer("Please enter a positive value for calories per gram:")
                return
        elif field == "food_name":
            existing_food = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM Foods WHERE food_name = $1 AND user_id = $2)",
                value, message.from_user.id
            )
            if existing_food:
                await message.answer("This food name already exists. Try a different name:")
                return

        await conn.execute(f"""
            UPDATE Foods
            SET {field} = $1
            WHERE food_id = $2 AND user_id = $3
        """, value, food_id, message.from_user.id)
        await message.answer("Food updated successfully!", reply_markup=await get_main_menu())
        await state.clear()
    except ValueError:
        await message.answer(f"Please enter a valid value for {field.replace('_', ' ')}:")
    except Exception as e:
        logger.error(f"Error in update: {e}")
        await message.answer("An error occurred. Please try again.")
    finally:
        await conn.close()

@dp.callback_query(lambda c: c.data.startswith("delete_"))
async def delete_food_callback(callback: types.CallbackQuery):
    food_id = int(callback.data.split("_")[1])
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        await conn.execute("DELETE FROM Foods WHERE food_id = $1 AND user_id = $2", food_id, callback.from_user.id)
        await callback.message.answer("Food deleted successfully!", reply_markup=await get_main_menu())
    finally:
        await conn.close()
    await callback.answer()

async def main():
    await init_db()
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())