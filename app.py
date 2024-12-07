import os
from dotenv import load_dotenv
import openai
from openai import OpenAI
from quart import Quart, render_template, websocket
import asyncio
import json
import uuid  # Use UUIDs for persistent user IDs
import psycopg2
from psycopg2.extras import Json

app = Quart(__name__)

# Initialize OpenAI API client
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Queues for user management
waiting_room = []
active_users = {}  # Active users as {user1: user2, user2: user1}
user_languages = {}  # Language preferences for each user
conversation_mapping = {}  # Maps users to their conversation_id
user_presurveys = {}

# WebSocket-to-UUID mapping for persistent user IDs
websocket_to_uuid = {}

# Initialize OpenAI API client
openai.api_key = os.getenv("OPENAI_API_KEY")

# Database configuration
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT", "5432")
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)
    
@app.route('/')
async def index():
    return await render_template('index.html')

@app.websocket('/ws')
async def ws():
    global waiting_room, active_users
    current_user = websocket._get_current_object()
    websocket_id = id(current_user)  # Temporary ID for session tracking
    user_uuid = str(uuid.uuid4())  # Persistent ID for database operations

    # Map WebSocket ID to UUID
    websocket_to_uuid[current_user] = user_uuid
    print(f"[INFO] WebSocket {websocket_id} connected with UUID {user_uuid}.")

    # Wait for the user to send their language preference and presurvey
    language_message = await websocket.receive()
    language_data = json.loads(language_message)

    if language_data["type"] == "language":
        user_languages[current_user] = language_data["language"]
        print(f"[INFO] User {websocket_id} selected language: {user_languages[current_user]}")

        presurvey = {
            "qualityRating": language_data.get("question1"),
            "seamlessRating": language_data.get("question2"),
            "translationeseRating": language_data.get("question3")
        }
        user_presurveys[current_user] = presurvey
        print(f"[INFO] User {websocket_id} presurvey data stored temporarily: {presurvey}")

    # Add user to the waiting room
    waiting_room.append(current_user)

    # Wait until paired
    while current_user not in active_users:
        if len(waiting_room) >= 2:
            await pair_users()
        await asyncio.sleep(1)

    # Once paired, start chat
    partner = active_users[current_user]
    conversation_id = conversation_mapping.get(current_user)  # Get the conversation_id

    if conversation_id is not None:
        await start_chat(current_user, partner, conversation_id)
    else:
        print(f"[ERROR] Conversation ID not found for User {websocket_id}.")
        await current_user.close(code=1011)  # Close WebSocket with an error code
    # Cleanup after chat ends
    remove_user_from_active(current_user)


async def pair_users():
    global waiting_room, active_users, conversation_mapping

    if len(waiting_room) >= 2:
        user1 = waiting_room.pop(0)
        user2 = waiting_room.pop(0)

        active_users[user1] = user2
        active_users[user2] = user1

        conn = None

        # Retrieve UUIDs for users
        user1_id = websocket_to_uuid[user1]
        user2_id = websocket_to_uuid[user2]

        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO conversations (
                        user1_id, user2_id, user1_lang, user2_lang, "group", model, conversation_history, user1_presurvey, user2_presurvey
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING conversation_id
                """, (
                    user1_id, user2_id, user_languages[user1], user_languages[user2],
                    "control" if user_languages[user1] == user_languages[user2] else "experiment",
                    'gpt-4o-mini', Json([]), Json(user_presurveys[user1]), Json(user_presurveys[user2])
                ))
                conversation_id = cursor.fetchone()[0]
                conn.commit()

            print(f"[INFO] Paired User {user1_id} with User {user2_id} in conversation {conversation_id}.")

            conversation_mapping[user1] = conversation_id
            conversation_mapping[user2] = conversation_id

            # Notify users they are paired
            await asyncio.gather(
                user1.send(json.dumps({"type": "paired", "message": "You are now paired. Start chatting!", "conversation_id": conversation_id})),
                user2.send(json.dumps({"type": "paired", "message": "You are now paired. Start chatting!", "conversation_id": conversation_id}))
            )

            # Start the chat timer and the chat session concurrently
            chat_timer_task = asyncio.create_task(chat_timer_task(user1, user2))
            chat_task = asyncio.create_task(start_chat(user1, user2, conversation_id))

        except Exception as e:
            print(f"[ERROR] Failed to pair users or insert conversation into the database: {e}")
        finally:
            if conn:
                conn.close()

async def start_chat(user1, user2, conversation_id):
    conn = None
    survey_submitted = {user1: False, user2: False}  # Track survey submission for both users

    try:
        conn = get_db_connection()
        chat_ended = False

        while not chat_ended:
            user1_task = asyncio.create_task(user1.receive())
            user2_task = asyncio.create_task(user2.receive())

            done, pending = await asyncio.wait(
                [user1_task, user2_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in done:
                try:
                    message = json.loads(task.result())
                    if "type" not in message:
                        print(f"[ERROR] Missing 'type' in message: {message}")
                        continue

                    if message["type"] == "endChat":
                        print(f"[INFO] User {id(user1) if task == user1_task else id(user2)} ended the chat.")
                        chat_ended = True
                        await asyncio.gather(
                            user1.send(json.dumps({"type": "survey", "conversation_id": conversation_id, "message": f"Conversation {conversation_id} has ended."})),
                            user2.send(json.dumps({"type": "survey", "conversation_id": conversation_id, "message": f"Conversation {conversation_id} has ended."})),
                        )
                        print("[INFO] Sent survey prompts to both users.")

                    elif message["type"] == "survey":
                        sender = user1 if task == user1_task else user2

                        try:
                            # Decide the primary column based on the sender
                            primary_column = "user1_postsurvey" if sender == user1 else "user2_postsurvey"
                            secondary_column = "user2_postsurvey" if primary_column == "user1_postsurvey" else "user1_postsurvey"

                            # Check if columns are already filled
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    SELECT user1_postsurvey, user2_postsurvey
                                    FROM conversations
                                    WHERE conversation_id = %s
                                """, (conversation_id,))
                                result = cursor.fetchone()

                            user1_postsurvey, user2_postsurvey = result if result else (None, None)

                            # Determine where to store the survey
                            if not (user1_postsurvey if primary_column == "user1_postsurvey" else user2_postsurvey):
                                column = primary_column
                            elif not (user2_postsurvey if primary_column == "user1_postsurvey" else user1_postsurvey):
                                column = secondary_column
                            else:
                                print(f"[WARNING] Both columns are already filled for conversation {conversation_id}. Skipping.")
                                return  # Both surveys are already stored; do nothing

                            # Store the survey in the determined column
                            with conn.cursor() as cursor:
                                cursor.execute(f"""
                                    UPDATE conversations
                                    SET {column} = %s
                                    WHERE conversation_id = %s
                                """, (Json(message), conversation_id))
                                conn.commit()

                            print(f"[INFO] Stored {column} for User {id(sender)} in conversation {conversation_id}.")

                        except Exception as e:
                            print(f"[ERROR] Failed to store survey for User {id(sender)} in conversation {conversation_id}: {e}")

                        survey_submitted[sender] = True

                    elif message["type"] == "typing":
                        target_user = user2 if task == user1_task else user1
                        await target_user.send(json.dumps({"type": "typing", "status": "typing"}))

                    elif message["type"] == "stopTyping":
                        target_user = user2 if task == user1_task else user1
                        await target_user.send(json.dumps({"type": "typing", "status": "stopped"}))

                    elif message["type"] == "message" and "text" in message:
                        sender = user1 if task == user1_task else user2
                        receiver = user2 if task == user1_task else user1
                        translated_message = await translate_message(
                            message["text"],
                            user_languages[sender],
                            user_languages[receiver],
                        )
                        await receiver.send(json.dumps({"type": "message", "text": translated_message}))

                        # Update conversation history in the database
                        with conn.cursor() as cursor:
                            cursor.execute("""
                                UPDATE conversations
                                SET conversation_history = conversation_history || %s
                                WHERE conversation_id = %s
                            """, (
                                Json([{"sender": id(sender), "text": message["text"], "translation": translated_message}]),
                                conversation_id,
                            ))
                            conn.commit()

                    else:
                        print(f"[WARNING] Unhandled message type or missing 'text': {message}")

                except Exception as e:
                    print(f"[ERROR] Exception while processing message: {e}")

            # Cancel any remaining tasks after processing
            for task in pending:
                task.cancel()

    except Exception as e:
        print(f"[ERROR] Exception in start_chat: {e}")
    finally:
        if conn:
            conn.close()

        # Close connections only after all surveys are submitted
        await asyncio.gather(
            *[safe_close(user) for user, submitted in survey_submitted.items() if submitted],
        )
        print("[INFO] WebSocket connections closed.")


async def translate_message(message, source_language, target_language):
    """
    Translate the message using OpenAI API.
    """
    language_map = {
        "english": "English",
        "chinese": "Chinese",
        "spanish": "Spanish"
    }
    source = language_map.get(source_language, "English")
    target = language_map.get(target_language, "English")

    if source == target:
        return message  # No translation needed

    prompt = f"Translate the following {source} text to {target}: {message}. Answer with only the translated message."
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] OpenAI API call failed: {e}")
        return "Translation error."


async def chat_timer_task(user1, user2):
    """
    Timer task that runs for 3 minutes and sends periodic updates to users.
    Ends the chat when the timer expires.
    """
    try:
        total_time = 180  # Total chat duration in seconds
        print(f"[INFO] Timer started for users {id(user1)} and {id(user2)}.")
        for remaining_time in range(total_time, 0, -1):  # Countdown loop
            time_message = {
                "type": "timer",
                "remaining_time": remaining_time
            }
            # Send the remaining time to both users
            await user1.send(json.dumps(time_message))
            await user2.send(json.dumps(time_message))
            await asyncio.sleep(1)  # Wait 1 second

        # Time expired
        print("[INFO] Chat timer expired. Ending chat.")
        await asyncio.gather(
            user1.send(json.dumps({"type": "expired", "conversation_id": conversation_id, "message": "Chat timer has expired."})),
            user2.send(json.dumps({"type": "expired", "conversation_id": conversation_id, "message": "Chat timer has expired."}))
        )
    except asyncio.CancelledError:
        print(f"[INFO] Chat timer cancelled for users {id(user1)} and {id(user2)}.")


async def safe_close(websocket):
    """
    Safely close a WebSocket connection, catching any exceptions.
    """
    try:
        await websocket.close(code=1000)
        print(f"[INFO] WebSocket {id(websocket)} closed successfully.")
    except Exception as e:
        print(f"[ERROR] Error while closing WebSocket {id(websocket)}: {e}")


def remove_user_from_active(user):
    """
    Remove a user from active_users and clean up their partner.
    """
    global active_users
    if user in active_users:
        partner = active_users.pop(user, None)
        if partner:
            active_users.pop(partner, None)
            print(f"[INFO] Removed User {id(user)} and their partner {id(partner)} from active_users.")


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)