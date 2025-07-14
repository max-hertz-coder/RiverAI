import openai
from worker import config

# If multiple API keys are provided, cycle through them
_key_index = 0
if config.OPENAI_API_KEYS:
    openai.api_key = config.OPENAI_API_KEYS[0]

def get_next_api_key():
    global _key_index
    if not config.OPENAI_API_KEYS:
        return None
    key = config.OPENAI_API_KEYS[_key_index]
    _key_index = (_key_index + 1) % len(config.OPENAI_API_KEYS)
    return key

async def ask_gpt(messages, model="gpt-3.5-turbo"):
    """
    Send a list of messages (conversation) to OpenAI ChatCompletion API.
    Returns the assistant's reply text.
    """
    # Rotate API keys if multiple
    api_key = get_next_api_key()
    if api_key:
        openai.api_key = api_key
    try:
        # Use async API call
        response = await openai.ChatCompletion.acreate(
            model=model,
            messages=messages,
            temperature=0.7
        )
        answer = response.choices[0].message.content
        return answer
    except Exception as e:
        # Log or print error
        return f"Ошибка GPT: {e}"
