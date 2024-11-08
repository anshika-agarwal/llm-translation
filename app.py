import os
from dotenv import load_dotenv
import openai
from openai import OpenAI
from quart import Quart, render_template, websocket
import asyncio
import json

app = Quart(__name__)

# Queue to store available users waiting for pairing
available_users = []

# Dictionary to store language preferences for each user
user_languages = {}

# Initialize OpenAI API client
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route('/')
async def index():
    return await render_template('index.html')


@app.websocket('/ws')
async def ws():
    global available_users
    current_user = websocket._get_current_object()
    user_id = id(current_user)
    print(f"[INFO] User {user_id} connected and waiting for a partner.")

    # Wait for the user to send their language preference
    language_message = await websocket.receive()
    language_data = json.loads(language_message)
    if language_data["type"] == "language":
        user_languages[current_user] = language_data["language"]
        print(f"[INFO] User {user_id} selected language: {language_data['language']}")

    # Add user to queue and wait briefly to pair
    available_users.append(current_user)
    await asyncio.sleep(1)

    # Pair users if possible
    if len(available_users) > 1:
        user1 = available_users.pop(0)
        user2 = available_users.pop(0)
        await user1.send("Paired! You can now chat.")
        await user2.send("Paired! You can now chat.")
        print(f"[INFO] Paired User {id(user1)} with User {id(user2)}.")

        # Relay messages between users with translation
        await handle_pair(user1, user2)
    else:
        await websocket.send("Waiting for a partner to connect...")
        await keep_alive(current_user)


async def handle_pair(user1, user2):
    try:
        while True:
            user1_task = asyncio.create_task(user1.receive())
            user2_task = asyncio.create_task(user2.receive())

            done, pending = await asyncio.wait(
                [user1_task, user2_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            if user1_task in done:
                message = json.loads(user1_task.result())["text"]
                translated_message = await translate_message(message, user_languages[user1], user_languages[user2])
                await user2.send(translated_message)

            if user2_task in done:
                message = json.loads(user2_task.result())["text"]
                translated_message = await translate_message(message, user_languages[user2], user_languages[user1])
                await user1.send(translated_message)

            for task in pending:
                task.cancel()

    except Exception as e:
        print(f"[ERROR] Exception in handle_pair: {e}")


async def translate_message(message, source_language, target_language):
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
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()


async def keep_alive(user):
    try:
        while True:
            await asyncio.sleep(10)
            await user.send("ping")
            print(f"[INFO] Sent 'ping' to User {id(user)} to keep connection alive.")
    except Exception as e:
        print(f"[INFO] Connection closed for User {id(user)}: {e}")


if __name__ == '__main__':
    app.run()
