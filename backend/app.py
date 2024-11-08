from quart import Quart
from controllers import chat, submit_survey
from database import init_db

app = Quart(__name__)

from quart import Quart
from controllers import chat, submit_survey
from database import init_db

app = Quart(__name__)

@app.before_serving
async def startup():
    await init_db()

@app.route("/")
async def index():
    return await render_template("index.html")

@app.websocket("/ws")
async def chat_route():
    await chat()

@app.route("/survey", methods=['POST'])
async def survey_route():
    return await submit_survey()

if __name__ == "__main__":
    app.run(port=5000)


# from quart import Quart, websocket, render_template
# import asyncio
# import uuid
# import os
# from openai import OpenAI
# import asyncpg
# from dotenv import load_dotenv

# load_dotenv()

# # Quart app and OpenAI setup
# app = Quart(__name__)

# # Initialize OpenAI
# openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# # PostgreSQL configuration
# DATABASE_URL = os.getenv("DATABASE_URL")
# db_pool = None

# # Global waiting room and active chat pairs
# waiting_room = []
# active_chats = {}

# async def init_db():
#     global db_pool
#     db_pool = await asyncpg.create_pool(DATABASE_URL)

# @app.before_serving
# async def startup():
#     await init_db()

# async def match_users():
#     """Match users in the waiting room and set up active chat pairs."""
#     while True:
#         if len(waiting_room) >= 2:
#             user1 = waiting_room.pop(0)
#             user2 = waiting_room.pop(0)

#             active_chats[user1['id']] = {
#                 "ws": user1['ws'],
#                 "partner_id": user2['id'],
#                 "language": user1['language']
#             }
#             active_chats[user2['id']] = {
#                 "ws": user2['ws'],
#                 "partner_id": user1['id'],
#                 "language": user2['language']
#             }

#             await user1['ws'].send_json({
#                 "type": "matched",
#                 "partnerId": user2['id'],
#                 "partnerLanguage": user2['language']
#             })
#             await user2['ws'].send_json({
#                 "type": "matched",
#                 "partnerId": user1['id'],
#                 "partnerLanguage": user1['language']
#             })
#         await asyncio.sleep(1)

# async def translate_message_using_openai(message, from_lang, to_lang):
#     """Translate a message using OpenAI."""
#     try:
#         response = await openai.Completion.create(
#             model="gpt-3.5-turbo",
#             prompt=f"Translate the following from {from_lang} to {to_lang}: {message}",
#             max_tokens=100,
#             temperature=0.3
#         )
#         return response.choices[0].text.strip()
#     except Exception as e:
#         print("Translation error:", e)
#         return message

# async def save_conversation(user_id, original_message, translated_message, from_language, to_language):
#     """Save a conversation to the database."""
#     async with db_pool.acquire() as conn:
#         await conn.execute(
#             "INSERT INTO conversations (user_id, original_message, translated_message, from_language, to_language) VALUES ($1, $2, $3, $4, $5)",
#             user_id, original_message, translated_message, from_language, to_language
#         )

# async def save_survey_response(user_id, rating, feedback):
#     """Save a survey response to the database."""
#     async with db_pool.acquire() as conn:
#         await conn.execute(
#             "INSERT INTO survey_responses (user_id, rating, feedback) VALUES ($1, $2, $3)",
#             user_id, rating, feedback
#         )

# @app.route("/")
# async def index():
#     """Render the main chat page."""
#     return await render_template("chat.html")

# @app.websocket("/ws")
# async def chat():
#     """Handle WebSocket connections."""
#     user_id = str(uuid.uuid4())
#     user_ws = websocket._get_current_object()
    
#     await websocket.send_json({"type": "userId", "userId": user_id})

#     # Wait for the initial join message with language
#     join_data = await websocket.receive_json()
#     if join_data.get("type") == "join":
#         language = join_data.get("language")
#         waiting_room.append({"ws": user_ws, "id": user_id, "language": language})

#         await match_users()

#     while True:
#         try:
#             message = await websocket.receive_json()
#             if message['type'] == 'chatMessage':
#                 chat = active_chats.get(message['userId'])
#                 if chat:
#                     translated_message = await translate_message_using_openai(
#                         message['message'],
#                         message['fromLanguage'],
#                         active_chats[chat['partner_id']]['language']
#                     )

#                     # Send the message to the partner
#                     await chat['ws'].send_json({
#                         "type": "message",
#                         "original": message['message'],
#                         "translated": translated_message,
#                         "fromUserId": message['userId']
#                     })

#                     # Save the conversation
#                     await save_conversation(
#                         message['userId'],
#                         message['message'],
#                         translated_message,
#                         message['fromLanguage'],
#                         active_chats[chat['partner_id']]['language']
#                     )

#             elif message['type'] == 'survey':
#                 await save_survey_response(
#                     message['userId'],
#                     message['rating'],
#                     message['feedback']
#                 )

#         except Exception as e:
#             print("Error handling message:", e)
#             break

# @app.websocket('/disconnect')
# async def handle_disconnect(user_id):
#     global waiting_room
#     waiting_room = [user for user in waiting_room if user['id'] != user_id]

#     if user_id in active_chats:
#         partner_id = active_chats[user_id]['partner_id']
#         if partner_id in active_chats:
#             await active_chats[partner_id]['ws'].send_json({"type": "partnerDisconnected"})
#             del active_chats[partner_id]
#         del active_chats[user_id]

# if __name__ == "__main__":
#     app.run(port=5000)
