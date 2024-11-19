# Getting started

This application is dockerized. Take a look at [Dockerfile](/app/Dockerfile) to see how it works.

A very simple [docker-compose.yml](/docker-compose.yml) has been included to support local development and deployment. Take a look at [docker-compose.yml](/docker-compose.yml) for more information.

## Prerequisites

1. Install the version of Python specified in [.python-version](/app/.python-version)
   [pyenv](https://github.com/pyenv/pyenv#installation) is one popular option for installing Python,
   or [asdf](https://asdf-vm.com/).

2. After installing and activating the right version of Python, install
   [poetry](https://python-poetry.org/docs/#installation) and follow the instructions to add poetry to your path if necessary.

   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

3. If you are using an M1 mac, you will need to install postgres as well: `brew install postgresql` (The psycopg2-binary is built from source on M1 macs which requires the postgres executable to be present)

4. You'll also need [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

## Run the application

**Note:** Run everything from within the `/app` folder:

1. Set up an (empty) local secrets file: `touch .env` and copy the provided example Docker override: `cp ../docker-compose.override.yml.example ../docker-compose.override.yml`
2. Download the embedding model into the `models` directory: `git clone https://huggingface.co/sentence-transformers/multi-qa-mpnet-base-cos-v1 models/multi-qa-mpnet-base-cos-v1`
3. Run `make init start` to build the image and start the container.
4. Navigate to `localhost:8000/chat` to access the Chainlit UI.
5. Run `make run-logs` to see the logs of the running application container
6. Run `make stop` when you are done to delete the container.

## Next steps

Now that you're up and running, read the [application docs](README.md) to familiarize yourself with the application.

### Installing Ollama

You can install ollama on macOSX by calling `brew install ollama`, for other operating systems or the desktop app see the [Ollama repository](https://github.com/ollama/ollama).

To download a model run `ollama pull <model_name>`

Ex: `ollama pull llama2:7b`

To start Ollama without the desktop app run `ollama serve`

To configure a local secret to enable Ollama locally add `OLLAMA_HOST=http://host.docker.internal:11434` to your `.env` file.

### Start a Jupyter notebook

We use Jupyter notebooks for saving and sharing exploratory code. You can open and run these notebooks (and make a new one) with `make notebook`. You will see output like:

```
    To access the server, open this file in a browser:
        file:///home/yourusername/.local/share/jupyter/runtime/jpserver-13-open.html
    Or copy and paste one of these URLs:
        http://20cb9005b18b:8888/tree?token=2d1215943f468b3aefb67b353bf1ff8599cee13c1da74172
        http://127.0.0.1:8888/tree?token=2d1215943f468b3aefb67b353bf1ff8599cee13c1da74172
```

Copy and paste the provided URL that starts with http://127.0.0.1:8888 to access Jupyter.

## Running the Chat API
The Chat API is intended for other applications to make requests to the chatbot.
Running the Chainlit app will also run the API, if `app_config.enable_chat_api=True`.

### Running only the API (without Chainlit) in local env
1. Run `make launch-api-only`
1. Check that the API is up, open a browser to http://localhost:8001/api_healthcheck.
1. Browse to http://localhost:8001/docs to try out the API.

## Terminology

### Relevant to data source ingestion
- Document: a PDF file, web page, etc.
    - A document may have headings and sections.
    - Document content (i.e., text) is parsed, partitioned, and stored into a vector DB for use in RAG.
- Chunk: a size-limited block of text stored in the vector DB
    - Document text must be partitioned into chunks for storage and retrieval.
    - Natural delineations in the text should be used to create separate chunks so that text in a chunk is topically cohesive.
    - Due to the size limit, cohesive text must be split into separate chunks. For example, a single list of many bullets and/or long texts must be split. Paragraph(s) introducing the list should be included in each chunk or associated with each chunk to provide context. Similarly, long document sections need to be split, preferably at paragraph breaks. For context, it may be useful to provide summaries of prior paragraphs in the chunk, in addition to headings.

### Relevant to Retrieval (the 'R' in RAG)
- Citation: user-friendly, short-length text for reference
    - While chunk texts are size-limited, they are still too lengthy to present to users.
    - A citation is a subsection within chunk text.
- Subsection: substring within chunk text
    - For each retrieved chunk, the chunk text is partitioned into subsections.
    - The subsections are assigned an identifier for an LLM to choose relevant subsections, which are presented to the user as citations.

### Prompt Anatomy (the 'G' in RAG)
A prompt is sent to the LLM to have it generate an answer to a question.

An LLM prompt consists of:
- **System prompt** sets the LLM's role, tone, style; e.g. "You are …", "Act as ..."
- **Chat history** used by the LLM as its conversational memory
- **Context** offers background or relevant information, including retrieved chunk texts for RAG
- **Instruction** a.k.a. query or question
- **Content** to which the instruction is applied (e.g., for "Summarize the content")
- **Examples** of questions and answers; used for in-context learning (ICL)
- **Cue** is the prefix for the answer that the LLM will complete
