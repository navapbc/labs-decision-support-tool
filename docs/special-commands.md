# Special commands

The chatbot supports special commands that can be accessed via the Chainlit interface (e.g., `http://localhost:8000/chat` when running locally, or `/chat` in a deployed environment). These commands are intended to make to it easier for researchers to interact with the chatbot.

## Batch processing

To have answers generated for multiple questions at once, create a .csv file with a `question` column, for example:

```
question
"What is the base period for SDI?"
"Where can I find the Spanish version of the claims information?"
"What types of support does the program offer for individuals recovering from an illness or injury?"
```

Then, in the chat interface, submit the message `Batch processing` to the chatbot and upload the .csv file when prompted.

The input file can have additional columns beyond `question`. They will be preserved in the output file, in addition to the response columns.

## Export logs

User interactions are stored in LiteralAI. These logs can be exported by submitting the message `Export LiteralAI` and following up with a date range, e.g., `2025-03-04 2025-03-06`. The second date is exclusive; the previous command will export logs from 3/4 and 3/5, but not 3/6.