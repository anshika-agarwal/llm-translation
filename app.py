import os
from dotenv import load_dotenv
import openai
from openai import OpenAI
from quart import Quart, render_template, websocket
import asyncio
import json

app = Quart(__name__)

# Initialize OpenAI API client
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Queues for user management
waiting_room = []
active_users = {}  # Active users as {user1: user2, user2: user1}
user_languages = {}  # Language preferences for each user

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
    user_id = id(current_user)
    print(f"[INFO] User {user_id} connected and waiting for a partner.")

    # Wait for the user to send their language preference
    language_message = await websocket.receive()
    language_data = json.loads(language_message)
    if language_data["type"] == "language":
        user_languages[current_user] = language_data["language"]
        print(f"[INFO] User {user_id} selected language: {language_data['language']}")

    # Add user to the waiting room
    waiting_room.append(current_user)

    # Wait until paired
    while current_user not in active_users:
        if len(waiting_room) >= 2:
            await pair_users()
        await asyncio.sleep(1)

    # Once paired, start chat
    partner = active_users[current_user]
    await start_chat(current_user, partner)

    # Cleanup after chat ends
    remove_user_from_active(current_user)


async def pair_users():
    """
    Pair two users from the waiting room and add them to active_users.
    """
    global waiting_room, active_users

    if len(waiting_room) >= 2:
        user1 = waiting_room.pop(0)
        user2 = waiting_room.pop(0)

        active_users[user1] = user2
        active_users[user2] = user1

        # Notify both users they are paired
        asyncio.create_task(user1.send(json.dumps({"type": "paired", "message": "You are now paired. Start chatting!"})))
        asyncio.create_task(user2.send(json.dumps({"type": "paired", "message": "You are now paired. Start chatting!"})))

        print(f"[INFO] Paired User {id(user1)} with User {id(user2)}.")

        # Start the chat timer and the chat session concurrently
        asyncio.create_task(chat_timer_task(user1, user2))
        asyncio.create_task(start_chat(user1, user2))        


async def start_chat(user1, user2):
    """
    Handle chat between two paired users.
    Ends when a user sends an endChat message or the timer expires.
    """
    try:
        chat_ended = False  # Track whether the chat has already ended

        while not chat_ended:
            user1_task = asyncio.create_task(user1.receive())
            user2_task = asyncio.create_task(user2.receive())

            done, pending = await asyncio.wait(
                [user1_task, user2_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if user1_task in done:
                message = json.loads(user1_task.result())
                if message["type"] == "endChat":
                    print(f"[INFO] User {id(user1)} ended the chat.")
                    chat_ended = True
                    await end_chat_for_both(user1, user2)
                    break
                elif message["type"] == "typing":
                    # Notify the other user that user1 is typing
                    await user2.send(json.dumps({"type": "typing", "status": "typing"}))
                elif message["type"] == "stopTyping":
                    # Notify the other user that user1 stopped typing
                    await user2.send(json.dumps({"type": "typing", "status": "stopped"}))
                else:
                    translated_message = await translate_message(message["text"], user_languages[user1], user_languages[user2])
                    await user2.send(json.dumps({"type": "message", "text": translated_message}))

            if user2_task in done:
                message = json.loads(user2_task.result())
                if message["type"] == "endChat":
                    print(f"[INFO] User {id(user2)} ended the chat.")
                    chat_ended = True
                    await end_chat_for_both(user1, user2)
                    break
                elif message["type"] == "typing":
                    # Notify the other user that user2 is typing
                    await user1.send(json.dumps({"type": "typing", "status": "typing"}))
                elif message["type"] == "stopTyping":
                    # Notify the other user that user2 stopped typing
                    await user1.send(json.dumps({"type": "typing", "status": "stopped"}))
                else:
                    translated_message = await translate_message(message["text"], user_languages[user2], user_languages[user1])
                    await user1.send(json.dumps({"type": "message", "text": translated_message}))

            for task in pending:
                task.cancel()  # Cancel remaining tasks

    except Exception as e:
        print(f"[ERROR] Exception in start_chat: {e}")


async def end_chat_for_both(user1, user2):
    """
    Ends the chat for both users, notifies them, and sends a survey.
    """
    print(f"[INFO] Ending chat between User {id(user1)} and User {id(user2)}.")
    survey = {
        "type": "survey",
        "questions": [
            "How engaging was your conversation?",
            "How friendly was your conversation?",
            "How would you rate the overall quality of the conversation?",
            "Do you believe your chat partner was a native speaker?"
        ]
    }
    try:
        # Send the survey to both users
        await user1.send(json.dumps(survey))
        await user2.send(json.dumps(survey))

        # Close the WebSocket connections with a normal close code (1000)
        await user1.close(code=1000)
        await user2.close(code=1000)
    except Exception as e:
        print(f"[ERROR] Error while sending survey or closing connections: {e}")


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

    prompt = f"Translate the following {source} text to {target}: {message}"
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
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
        await end_chat_for_both(user1, user2)
    except asyncio.CancelledError:
        print(f"[INFO] Chat timer cancelled for users {id(user1)} and {id(user2)}.")



if __name__ == '__main__':
    app.run()
