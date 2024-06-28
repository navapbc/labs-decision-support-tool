import json

from litellm import completion


def mock_completion(model, messages):
    # Convert the messages list of dictionaries to a string
    messages = json.dumps(messages, sort_keys=True)
    mock_response = f"Called {model} with {messages}"
    return completion(
        model,
        messages,
        mock_response=mock_response)