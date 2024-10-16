import json

from litellm import completion


def mock_completion(model, messages, **kwargs):
    # Convert the messages list of dictionaries to a string
    messages = json.dumps(messages, sort_keys=True)
    # Strip generated JSON of escaped newlines to make it simple to compare with prompts
    messages = messages.replace("\\n", "\n")
    mock_response = f"Called {model} with {messages}"
    return completion(model, messages, mock_response=mock_response)
