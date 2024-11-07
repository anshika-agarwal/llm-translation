const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const { Configuration, OpenAIApi } = require('openai');
const { Pool } = require('pg');
const { v4: uuidv4 } = require('uuid');
require('dotenv').config();

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Serve static files
app.use(express.static('public'));

// OpenAI API Configuration
const configuration = new Configuration({
    apiKey: process.env.OPENAI_API_KEY
});
const openai = new OpenAIApi(configuration);

// PostgreSQL Configuration
const pool = new Pool({
    user: process.env.DB_USER,
    host: process.env.DB_HOST,
    database: process.env.DB_NAME,
    password: process.env.DB_PASSWORD,
    port: process.env.DB_PORT || 5432,
});

let waitingRoom = [];
let activeChats = {};

function matchUsers() {
    if (waitingRoom.length >= 2) {
        const user1 = waitingRoom.shift();
        const user2 = waitingRoom.shift();

        activeChats[user1.id] = {
            ws: user1.ws,
            partnerId: user2.id,
            language: user1.language
        };
        activeChats[user2.id] = {
            ws: user2.ws,
            partnerId: user1.id,
            language: user2.language
        };

        user1.ws.send(JSON.stringify({
            type: 'matched',
            partnerId: user2.id,
            partnerLanguage: user2.language
        }));
        user2.ws.send(JSON.stringify({
            type: 'matched',
            partnerId: user1.id,
            partnerLanguage: user1.language
        }));
    }
}

function handleDisconnect(userId) {
    waitingRoom = waitingRoom.filter(user => user.id !== userId);

    if (activeChats[userId]) {
        const partnerId = activeChats[userId].partnerId;
        if (activeChats[partnerId]) {
            activeChats[partnerId].ws.send(JSON.stringify({ 
                type: 'partnerDisconnected' 
            }));
            delete activeChats[partnerId];
        }
        delete activeChats[userId];
    }
}

async function translateMessageUsingOpenAI(message, fromLang, toLang) {
    try {
        const response = await openai.createChatCompletion({
            model: 'gpt-3.5-turbo',
            messages: [{
                role: 'system',
                content: `You are a translator. Translate from ${fromLang} to ${toLang}. Provide only the translation, no explanations.`
            }, {
                role: 'user',
                content: message
            }],
            temperature: 0.3
        });
        return response.data.choices[0].message.content.trim();
    } catch (error) {
        console.error('Translation error:', error);
        return message;
    }
}

async function saveConversation(userId, originalMessage, translatedMessage, fromLanguage, toLanguage) {
    const query = `
        INSERT INTO conversations (user_id, original_message, translated_message, from_language, to_language)
        VALUES ($1, $2, $3, $4, $5)
    `;
    try {
        await pool.query(query, [userId, originalMessage, translatedMessage, fromLanguage, toLanguage]);
    } catch (err) {
        console.error('Error saving conversation:', err);
    }
}

async function saveSurveyResponse(userId, rating, feedback) {
    const query = `
        INSERT INTO survey_responses (user_id, rating, feedback)
        VALUES ($1, $2, $3)
    `;
    try {
        await pool.query(query, [userId, rating, feedback]);
    } catch (err) {
        console.error('Error saving survey response:', err);
    }
}

wss.on('connection', (ws) => {
    ws.onopen = () => {
        console.log('WebSocket connection established');
        document.getElementById('sendButton').disabled = false; // Enable the send button
        ws.send(JSON.stringify({
            type: 'join',
            language: userLanguage
        }));
    };

    ws.on('message', async (message) => {
        const data = JSON.parse(message);

        switch (data.type) {
            case 'join':
                const userId = uuidv4();
                waitingRoom.push({
                    ws,
                    id: userId,
                    language: data.language
                });
                ws.send(JSON.stringify({
                    type: 'userId',
                    userId: userId
                }));
                matchUsers();
                break;

            case 'chatMessage':
                const chat = activeChats[data.userId];
                if (chat) {
                    const translatedMessage = await translateMessageUsingOpenAI(
                        data.message,
                        data.fromLanguage,
                        activeChats[chat.partnerId].language
                    );
                    
                    chat.ws.send(JSON.stringify({
                        type: 'message',
                        original: data.message,
                        translated: translatedMessage,
                        fromUserId: data.userId
                    }));

                    await saveConversation(
                        data.userId,
                        data.message,
                        translatedMessage,
                        data.fromLanguage,
                        activeChats[chat.partnerId].language
                    );
                }
                break;

            case 'survey':
                await saveSurveyResponse(
                    data.userId,
                    data.rating,
                    data.feedback
                );
                break;
        }
    });

    ws.on('close', () => {
        const userId = Object.keys(activeChats).find(key => activeChats[key].ws === ws);
        if (userId) {
            handleDisconnect(userId);
        }
    });
});

const PORT = process.env.PORT || 5000;
server.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});