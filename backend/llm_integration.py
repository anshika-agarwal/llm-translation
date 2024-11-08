import os
from openai import OpenAI
openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def translate_message_using_openai(message, from_lang, to_lang):
    try:
        response = await openai.Completion.create(
            model="gpt-3.5-turbo",
            prompt=f"Translate the following from {from_lang} to {to_lang}: {message}",
            max_tokens=100,
            temperature=0.3
        )
        return response.choices[0].text.strip()
    except Exception as e:
        print("Translation error:", e)
        return message
