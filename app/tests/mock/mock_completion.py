import json

from litellm import completion


def mock_completion(model, messages, **kwargs):
    # Convert the messages list of dictionaries to a string
    messages_as_text = json.dumps(messages, sort_keys=True)
    # Strip generated JSON of escaped newlines to make it simple to compare with prompts
    messages_as_text = messages_as_text.replace("\\n", "\n")
    # Also strip generated JSON of escaped double quotes
    messages_as_text = messages_as_text.replace('\\"', '"')
    mock_response = f"Called {model} with {messages_as_text}"
    return completion(model, messages, mock_response=mock_response)
