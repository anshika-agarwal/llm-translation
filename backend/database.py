import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL")
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
