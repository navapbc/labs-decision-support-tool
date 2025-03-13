# Special commands

The chatbot supports special commands that can be accessed via the Chainlit interface (e.g., `http://localhost:8000/chat` when running locally, or `/chat` in a deployed environment). These commands are intended to make to it easier for researchers to interact with the chatbot.

While the commands aren't case-sensitive, their format is (e.g., dates need to follow the YYYY-MM-DD format described below). Additionally, when a special command is entered, the application will revert to normal behavior (the chatbot) if a follow-up response from the user isn't received within three minutes. If you get an unexpected response back to uploading a file or providing a data range such as "I'm not sure how to help you with that," start over from the beginning by re-entering the original command.

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