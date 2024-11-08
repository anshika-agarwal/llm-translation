import asyncio
import uuid
from quart import websocket, request, jsonify
from openai_integration import translate_message_using_openai
from database import save_conversation, save_survey_response

waiting_room = []
active_chats = {}

async def match_users():
    while len(waiting_room) >= 2:
        user1 = waiting_room.pop(0)
        user2 = waiting_room.pop(0)
        active_chats[user1['id']] = {"ws": user1['ws'], "partner_id": user2['id']}
        active_chats[user2['id']] = {"ws": user2['ws'], "partner_id": user1['id']}
        await user1['ws'].send_json({"type": "matched", "partnerId": user2['id']})
        await user2['ws'].send_json({"type": "matched", "partnerId": user1['id']})
        await asyncio.sleep(1)

async def chat():
    user_id = str(uuid.uuid4())
    user_ws = websocket._get_current_object()
    await websocket.send_json({"type": "userId", "userId": user_id})

    join_data = await websocket.receive_json()
    if join_data.get("type") == "join":
        language = join_data.get("language")
        waiting_room.append({"ws": user_ws, "id": user_id, "language": language})
        await match_users()

    while True:
        message = await websocket.receive_json()
        if message['type'] == 'chatMessage':
            partner = active_chats.get(user_id)
            if partner:
                translated_message = await translate_message_using_openai(
                    message['message'], message['fromLanguage'], partner['language']
                )
                await partner['ws'].send_json({"type": "message", "original": message['message'], "translated": translated_message})
                await save_conversation(user_id, message['message'], translated_message, message['fromLanguage'], partner['language'])

async def submit_survey():
    data = await request.get_json()
    await save_survey_response(data['userId'], data['rating'], data['feedback'])
    return jsonify({"message": "Survey submitted successfully"}), 201
