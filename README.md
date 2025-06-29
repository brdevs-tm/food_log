# 🥗 Nutrition Diary Bot

A Telegram bot to help users keep track of their daily food intake and calories. Built with `aiogram` and backed by a PostgreSQL database, the bot enables users to log their meals, monitor calorie consumption, and view insightful summaries.

---

## 🚀 Features

- 🍽️ Log foods with specific gram quantity
- 🔢 Automatically calculate and store total calorie intake
- 📊 View daily and weekly summaries
- 📅 Tracks user logs day-by-day
- 🧾 Stores data in structured PostgreSQL tables

---

## 🛠️ Technologies Used

- 🐍 Python 3.11+
- 🤖 [Aiogram 3.x](https://docs.aiogram.dev)
- 🐘 PostgreSQL
- 🔐 Asyncpg
- 📦 Dotenv for environment configuration

---

## 🧱 Database Schema

### 📌 Users
| Column      | Type    | Description               |
|-------------|---------|---------------------------|
| id          | SERIAL  | Primary key               |
| telegram_id | BIGINT  | Telegram user ID          |
| username    | TEXT    | Telegram username         |
| joined_at   | TIMESTAMP | Time of first interaction |

### 📌 Foods
| Column      | Type    | Description                   |
|-------------|---------|-------------------------------|
| id          | SERIAL  | Primary key                   |
| name        | TEXT    | Food name (e.g., Apple)       |
| calories_per_100g | INTEGER | Calories per 100 grams |

### 📌 DailyLog
| Column      | Type    | Description                        |
|-------------|---------|------------------------------------|
| id          | SERIAL  | Primary key                        |
| user_id     | INTEGER | FK → Users(id)                    |
| food_id     | INTEGER | FK → Foods(id)                    |
| grams       | INTEGER | Amount of food in grams            |
| calories    | INTEGER | Calculated calories                |
| logged_at   | TIMESTAMP | When the log was added            |

---

## ⚙️ Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/brdevs-tm/food-log.git
cd food-log
