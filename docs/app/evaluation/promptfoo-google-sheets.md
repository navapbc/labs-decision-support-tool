# Google Sheets Integration with PromptFoo for Chatbot Evaluation

This document outlines how to use promptfoo with Google Sheets to evaluate our chatbot's responses on various inputs and automatically score them.

## Overview

[promptfoo](https://promptfoo.dev/) is an evaluation framework for LLM outputs that allows us to:
- Define test cases for our chatbot
- Run evaluations against these test cases
- Score the outputs automatically
- View and share the results

By integrating with Google Sheets, we can:
- Collaborate on test cases in a familiar interface
- Run evaluations from the command line
- Write evaluation results back to the same or different sheets
- Share results easily with the team

## Setup Instructions

### 1. Install promptfoo and initialize the project

```bash
# From the project root
npm install -g promptfoo
npm install googleapis  # Peer dependency for Google Sheets integration
promptfoo init # This will create a promptfooconfig.yaml placeholder in your current directory
```

### 2. Create a Google Sheet for Test Cases (Publicly Accessible)

1. Create a new Google Sheet
2. Make it public (Share > Anyone with the link > Viewer)
3. Structure the sheet with the following columns:
   - Input variables for your test cases (e.g., `question`, `context`, `capability`)
   - `__expected` column for assertions/expectations

Example sheet structure:
| capability | question | __expected |
|------------|---------|------------|
| It should have the most recent benefit numerical values | What is the maximum benefit I can get as a single person from SNAP? | contains: 292 |
| It should know hot foods are not generally purchasable | Can I buy a rotisserie chicken with my SNAP benefits? | contains: NO |

### 3. Create a promptfoo Configuration File

Create a file named `promptfooconfig.yaml` in your project directory. See the [promptfoo-config-template.yaml](promptfoo-config-template.yaml) for a template.

### 3a. Creating a JavaScript Function for Unique Session IDs

Since promptfoo doesn't directly support built-in variables like `{{$uuid}}` or `{{$random}}`, we need to create a JavaScript function to generate unique session IDs:

1. Create a file named `generateUniqueId.js`, see the [generateUniqueId.js](generateUniqueId.js) file for an example.

2. Reference this file in your promptfoo configuration as shown above in the `defaultTest.vars` section.

### 4. Start the Chatbot Service

Before running the evaluation, make sure the chatbot service is running:

```bash
make start
```

This will start the chatbot service on `http://localhost:8000`.

### 5. Running Evaluations

Run the evaluation and output the results:

```bash
# Run evaluation with the default output
promptfoo eval -c promptfooconfig.yaml

# In a separate terminal, view the results in a web UI
promptfoo view
```

## Writing Results Back to Google Sheets

### Setting Up Google Authentication

To write results back to your Google Sheet, you'll need to set up Google's Default Application Credentials:

1. **Create a service account in Google Cloud Console**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Google Sheets API (sheets.googleapis.com)
   - Go to "Credentials" → "Create Credentials" → "Service Account"
   - Download the JSON key file

2. **Set up authentication**:
   ```bash
   # Set the environment variable for authentication
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-file.json"
   ```

3. **Share your Google Sheet with the service account**:
   - Open the JSON key file and find the "client_email" field (e.g. `example@navapbc.gserviceaccount.com`)
   - Share your Google Sheet with this email address, giving it "Editor" access

### Writing Results to the Same Sheet

Once authenticated, you can write evaluation results directly to your Google Sheet by adding an `outputPath` to your configuration:

```yaml
# yaml-language-server: $schema=https://promptfoo.dev/config-schema.json
description: 'Decision Support Tool Evaluation'
# ... existing configuration ...

# Input sheet for test cases (replace {sheetId} and {gid} with the actual sheet ID and gid)
tests: https://docs.google.com/spreadsheets/d/{sheetId}/edit?gid={gid}

# Option 1: Replace the existing tab for each evaluation including the gid (uncomment to use)
# outputPath: https://docs.google.com/spreadsheets/d/{sheetId}/edit?gid={gid}

# Option 2: Create a new tab for each evaluation excluding the gid (uncomment to use)
# outputPath: https://docs.google.com/spreadsheets/d/{sheetId}/edit
```

Alternatively, specify the output path directly on the command line:

```bash
promptfoo eval -c promptfooconfig.yaml -o https://docs.google.com/spreadsheets/d/{sheetId}/edit
```

### Exporting the Most Recent Evaluation

If you've already run an evaluation and want to export those results to a Google Sheet:

```bash
# Export the most recent evaluation to the Google Sheet (create a new tab)
promptfoo export latest --output https://docs.google.com/spreadsheets/d/{sheetId}/edit
```

You can find the evaluation ID in the output of your evaluation run, after "Evaluation complete. ID:". If you don't have the ID, you can use `latest` to export the most recent evaluation.

## Custom Evaluation Setup for Our Chatbot

The configuration shown above is set up to work specifically with our chatbot API endpoint at `/api/query`. The body parameters match our API's expected format:

- `chat_history`: The chat history (empty array for new sessions)
- `session_id`: A unique identifier for the session (generated by our JavaScript function)
- `new_session`: Whether to create a new session
- `message`: The question to ask the chatbot
- `user_id`: The user ID

The `transformResponse: "json ? json.response_text : ''"` field tells promptfoo to extract the `response_text` field from the API response as a string.

## Using Nunjucks Templating with promptfoo

Promptfoo uses Nunjucks templating for variable substitution in prompts and API requests. Key points to remember:

1. Variables from test cases are accessed using `{{variableName}}` syntax
2. For dynamic content like unique IDs, use JavaScript files referenced via `file://path/to/script.js`
3. Use `defaultTest.vars` to make variables available to all test cases
4. The JavaScript functions must return an object with an `output` property

## Troubleshooting

- **404 Not Found errors**: Ensure the chatbot service is running with `make start` before running the evaluation
- **Authentication errors**: If the API requires authentication, add appropriate headers to the config
- **Session already exists errors**: If you're getting errors about sessions already existing, ensure your `uniqueSessionId` function is generating truly unique IDs
- **Google Sheets access errors**: Make sure your service account has the proper permissions to the sheet

## Resources

- [promptfoo Documentation](https://promptfoo.dev/docs/intro)
- [promptfoo Google Sheets Integration](https://promptfoo.dev/docs/configuration/load-from-googlesheets)
- [Example Google Sheet Format](https://docs.google.com/spreadsheets/d/1eqFnv1vzkPvS7zG-mYsqNDwOzvSaiIAsKB3zKg9H18c/edit?usp=sharing) 