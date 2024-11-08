document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const joinBtn = document.getElementById('join-btn');
    const landing = document.getElementById('landing');
    const waiting = document.getElementById('waiting');
    const chatContainer = document.getElementById('chat-container');
    const chatMessages = document.getElementById('chat-messages');
    const messageInput = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const survey = document.getElementById('survey');
    const surveyForm = document.getElementById('survey-form');
    const userIdDisplay = document.getElementById('userIdDisplay');

    // Variables
    let ws;
    let userId;
    let userLanguage;

    // Event Listeners
    joinBtn.addEventListener('click', joinChat);
    sendBtn.addEventListener('click', sendMessage);
    surveyForm.addEventListener('submit', submitSurvey);

    function joinChat() {
        userLanguage = document.getElementById('language-select').value;
        if (!userLanguage) {
            alert('Please select a language');
            return;
        }

        landing.classList.add('hidden');
        waiting.classList.remove('hidden');

        ws = new WebSocket('ws://54.189.22.142:5000/ws');

        ws.onopen = function() {
            ws.send(JSON.stringify({ type: 'join', language: userLanguage }));
        };

        ws.onmessage = handleMessage;
        ws.onclose = handleDisconnect;
        ws.onerror = function(error) {
            console.error('WebSocket error:', error);
        };
    }

    function handleMessage(event) {
        const data = JSON.parse(event.data);

        switch (data.type) {
            case 'userId':
                userId = data.userId;
                userIdDisplay.textContent = `Your User ID: ${userId}`;
                break;

            case 'matched':
                waiting.classList.add('hidden');
                chatContainer.classList.remove('hidden');
                break;

            case 'message':
                displayMessage(data);
                break;

            case 'partnerDisconnected':
                alert('Your chat partner has disconnected.');
                chatContainer.classList.add('hidden');
                survey.classList.remove('hidden');
                ws.close();
                break;
        }
    }

    function handleDisconnect() {
        if (!survey.classList.contains('hidden')) return;
        chatContainer.classList.add('hidden');
        survey.classList.remove('hidden');
    }

    function sendMessage() {
        const message = messageInput.value.trim();
        if (!message) return;

        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: 'chatMessage',
                userId: userId,
                message: message,
                fromLanguage: userLanguage
            }));

            const messageDiv = document.createElement('div');
            messageDiv.className = 'message user';
            messageDiv.textContent = message;
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;

            messageInput.value = '';
        } else {
            alert('Connection is closed. Unable to send message.');
        }
    }

    function displayMessage(data) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message partner';

        const originalDiv = document.createElement('div');
        originalDiv.className = 'original';
        originalDiv.textContent = data.original;

        const translatedDiv = document.createElement('div');
        translatedDiv.className = 'translated';
        translatedDiv.textContent = data.translated;

        messageDiv.appendChild(originalDiv);
        messageDiv.appendChild(translatedDiv);

        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function submitSurvey(event) {
        event.preventDefault();
        const formData = new FormData(surveyForm);
        const surveyData = {
            userId: userId,
            rating: formData.get('rating'),
            helpful: formData.get('helpful'),
            comments: formData.get('comments'),
        };
        ws.send(JSON.stringify({ type: 'survey', ...surveyData }));
        alert('Survey submitted. Thank you!');
        surveyForm.reset();
        survey.classList.add('hidden');
        landing.classList.remove('hidden');
    }
});
