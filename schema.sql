-- Create Users table
CREATE TABLE IF NOT EXISTS Users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create Foods table
CREATE TABLE IF NOT EXISTS Foods (
    food_id SERIAL PRIMARY KEY,
    food_name TEXT UNIQUE NOT NULL,
    calories_per_gram FLOAT NOT NULL
);

-- Create DailyLog table
CREATE TABLE IF NOT EXISTS DailyLog (
    log_id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES Users(user_id),
    food_id INTEGER REFERENCES Foods(food_id),
    weight_grams FLOAT NOT NULL,
    calories FLOAT NOT NULL,
    log_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample foods
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