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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "database": os.getenv("DB_NAME", "food_log_bot"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "your_password"),
    "port": os.getenv("DB_PORT", "5432")
}

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Define FSM states for logging food
class LogFoodForm(StatesGroup):
    food_name = State()
    weight = State()

# Database initialization
async def init_db():
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        # Create tables
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS Users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS Foods (
                food_id SERIAL PRIMARY KEY,
                food_name TEXT UNIQUE NOT NULL,
                calories_per_gram FLOAT NOT NULL
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

        # Insert sample foods with calories per gram
        await conn.execute("""
            INSERT INTO Foods (food_name, calories_per_gram)
            VALUES
                ('Apple', 0.52),
                ('Chicken Breast', 1.65),
                ('Rice', 1.30),
                ('Banana', 0.89),
                ('Salmon', 2.08),
                ('Broccoli', 0.35),
                ('Bread', 2.65)
            ON CONFLICT (food_name) DO NOTHING;
        """)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    finally:
        await conn.close()

# Create main menu keyboard
async def get_main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍽️ Log Food"), KeyboardButton(text="📅 Daily Summary")],
            [KeyboardButton(text="📊 Weekly Summary")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Create food selection keyboard
async def get_food_keyboard():
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        foods = await conn.fetch("SELECT food_name FROM Foods")
        keyboard_buttons = [[KeyboardButton(text=food['food_name'])] for food in foods]
        keyboard = ReplyKeyboardMarkup(keyboard=keyboard_buttons, resize_keyboard=True)
        return keyboard
    finally:
        await conn.close()

# Register user in database
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

# Log food entry
async def log_food(user_id: int, food_name: str, weight: float):
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        food = await conn.fetchrow("""
            SELECT food_id, calories_per_gram
            FROM Foods
            WHERE food_name = $1
        """, food_name)
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

# Get daily summary
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
        return logs, total_calories
    finally:
        await conn.close()

# Get weekly summary
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
        return logs, total_calories
    finally:
        await conn.close()

# Command handlers
@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    await state.clear()
    await register_user(message.from_user)
    keyboard = await get_main_menu()
    await message.answer(
        "Welcome to the Daily Food Log Bot! 🍎\n"
        "Track your meals and calories. What would you like to do?",
        reply_markup=keyboard
    )

# Main menu handlers
@dp.message(lambda message: message.text == "🍽️ Log Food")
async def log_food_start(message: types.Message, state: FSMContext):
    await state.clear()
    keyboard = await get_food_keyboard()
    await message.answer(
        "Select a food item to log:",
        reply_markup=keyboard
    )
    await state.set_state(LogFoodForm.food_name)

@dp.message(lambda message: message.text == "📅 Daily Summary")
async def daily_summary(message: types.Message, state: FSMContext):
    await state.clear()
    logs, total_calories = await get_daily_summary(message.from_user.id, datetime.now())
    if not logs:
        await message.answer("No food logged for today. Start logging with 'wee Log Food'!", reply_markup=await get_main_menu())
        return

    response = f"Daily Summary ({datetime.now().strftime('%Y-%m-%d')}):\n\n"
    for log in logs:
        response += f"🍽️ {log['food_name']}: {log['weight_grams']}g ({log['calories']:.1f} kcal)\n"
    response += f"\nTotal Calories: {total_calories:.1f} kcal"
    await message.answer(response, reply_markup=await get_main_menu())

@dp.message(lambda message: message.text == "📊 Weekly Summary")
async def weekly_summary(message: types.Message, state: FSMContext):
    await state.clear()
    logs, total_calories = await get_weekly_summary(message.from_user.id, datetime.now())
    if not logs:
        await message.answer("No food logged for this week. Start logging with 'Log Food'!", reply_markup=await get_main_menu())
        return

    response = f"Weekly Summary (Last 7 Days):\n\n"
    for log in logs:
        response += f"📅 {log['log_day'].strftime('%Y-%m-%d')}: {log['daily_calories']:.1f} kcal\n"
    response += f"\nTotal Weekly Calories: {total_calories:.1f} kcal"
    await message.answer(response, reply_markup=await get_main_menu())

# Log food FSM handlers
@dp.message(LogFoodForm.food_name)
async def process_food_name(message: types.Message, state: FSMContext):
    food_name = message.text
    conn = await asyncpg.connect(**DB_CONFIG)
    try:
        food_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM Foods WHERE food_name = $1)", food_name
        )
        if not food_exists:
            await message.answer(
                "Please select a valid food from the keyboard below:",
                reply_markup=await get_food_keyboard()
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

async def main():
    # Initialize database
    await init_db()
    
    # Start polling
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())