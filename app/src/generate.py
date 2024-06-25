import dotenv
import os

from litellm import completion

dotenv.load_dotenv()

def get_models() -> dict[str, str]:
    """
    Returns a dictionary of the available models, based on
    which environment variables are set. The keys are the
    human-formatted model names, and the values are the model
    IDs for use with LiteLLM.
    """

    if "OPENAI_API_KEY" in os.environ:
        return {"OpenAI GPT-4o": "gpt-4o"}
    return {}

def generate(query: str) -> str:
    """
    Returns a string response from an LLM model, based on a query input.
    """
    messages = [
        {
            "content": """Provide answers in plain language written at the average American reading level. 
            Use bullet points. Keep your answers brief, max of 5 sentences. 
            Keep your answers as similar to your knowledge text as you can""",
            "role": "system",
        },
        {"content": query, "role": "user"},
    ]
    response = completion(model="gpt-3.5-turbo", messages=messages)
    return response['choices'][0]['message']['content']
