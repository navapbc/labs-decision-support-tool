# Nava Labs Decision Support Tool

Welcome! You are at the root of the Nava Labs Decision Support Tool pilot repo.

## Local Development

To set up your local development environment, follow the instructions in [Getting Started](docs/app/getting-started.md).

## Installing Ollama

You can install ollama on macOSX by calling `brew install ollama`, for other operating systems or the desktop app see the [Ollama repository](https://github.com/ollama/ollama).

To download a model run `ollama pull <model_name>`

Ex: `ollama pull llama2:7b`

To start Ollama without the desktop app run `ollama serve`

To configure a local secret to enable Ollama locally through docker add `OLLAMA_HOST=http://host.docker.internal:11434` to your `.env` file.

## Loading documents

The application supports loading Guru cards from .json files.

### Loading documents locally

To load a JSON file containing Guru cards in your local environment, from within `/app`:

```bash
make ingest-guru-cards FILEPATH=path/to/some_cards.json
```

The Docker container mounts the `/app` folder, so FILEPATH should be relative to `/app`. `/app/documents` is ignored by git, so is a good place for files you want to load but not commit.

### Loading documents in a deployed environment

The deployed application includes an S3 bucket, following the format `s3://decision-support-tool-app-<env>`, e.g., `s3://decision-support-tool-app-dev`.

After authenticating with AWS, from the root of this repo run:

```bash
aws s3 cp path/to/some_cards.json s3://decision-support-tool-app-dev/
./bin/run-command app <ENVIRONMENT> '["ingest-guru-cards", "s3://decision-support-tool-app-dev/some_cards.json"]'
```

Replace `<ENVIRONMENT>` with your environment, e.g., `dev`.
