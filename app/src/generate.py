import os


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
