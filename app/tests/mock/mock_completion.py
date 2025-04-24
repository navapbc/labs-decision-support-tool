import json
from types import SimpleNamespace

from litellm import completion


def mock_completion(model, messages, **kwargs):
    # Convert the messages list of dictionaries to a string
    messages_as_text = json.dumps(messages, sort_keys=True)
    # Strip generated JSON of escaped newlines to make it simple to compare with prompts
    messages_as_text = messages_as_text.replace("\\n", "\n")
    # Also strip generated JSON of escaped double quotes
    messages_as_text = messages_as_text.replace('\\"', '"')
    mock_response = f"Called {model} with {messages_as_text}"

    # If streaming is requested, return chunks instead
    if kwargs.get("stream", False):
        # Split into small chunks while preserving spaces
        chunk_size = 10
        chunks = []
        for i in range(0, len(mock_response), chunk_size):
            chunk = mock_response[i : i + chunk_size]
            chunks.append(
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=chunk))])
            )
        return chunks

    return completion(model, messages, mock_response=mock_response)
