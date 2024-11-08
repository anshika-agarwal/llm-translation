import asyncpg
import os

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
db_pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)

async def save_conversation(user_id, original_message, translated_message, from_language, to_language):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO conversations (user_id, original_message, translated_message, from_language, to_language) VALUES ($1, $2, $3, $4, $5)",
            user_id, original_message, translated_message, from_language, to_language
        )

async def save_survey_response(user_id, rating, feedback):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO survey_responses (user_id, rating, feedback) VALUES ($1, $2, $3)",
            user_id, rating, feedback
        )
