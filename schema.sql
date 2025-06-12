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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_food_user UNIQUE (food_name, user_id)
);

CREATE TABLE IF NOT EXISTS DailyLog (
    log_id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES Users(user_id),
    food_id INTEGER REFERENCES Foods(food_id),
    weight_grams FLOAT NOT NULL,
    calories FLOAT NOT NULL,
    log_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

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