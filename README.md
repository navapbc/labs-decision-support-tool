# Nava Labs Decision Support Tool

Welcome! You are at the root of the Nava Labs Decision Support Tool pilot repo. This repo contains code for a chatbot that answers questions about public benefit programs. It is powered by generative AI and retrieval-augmented-generation ("RAG") and intended for use by benefit navigators that have prior experience and familiarity with these programs.

## Project description

The chatbot ingests and parses documentation on policy programs, and then searches across this database of documentation to inform its responses. In March 2025, Nava began a pilot of this chatbot in partnership with [Imagine LA](https://www.imaginela.org/). Users of Imagine LA's [Benefit Navigator](https://www.imaginela.org/benefit-navigator) were provided access to a chatbot with access to documentation about CalWorks, CalFresh, Med-Cal, various tax credits and housing assistance programs, unemployment insurance, state disability insurance, paid family leave, and more.

## Project components

This project is built on Nava's open source [infrastructure template](https://github.com/navapbc/template-infra) and [Python application template](https://github.com/navapbc/template-application-flask/), part of [Nava's Platform](https://github.com/navapbc/platform).

 - The application is hosted in AWS, and the infrastructure is defined via Terraform in [/infra](https://github.com/navapbc/labs-decision-support-tool/tree/main/infra).
 - The application code is written in Python and is located in [/app/src](https://github.com/navapbc/labs-decision-support-tool/tree/main/app/src).
   - Chainlit and FastAPI are used to provide a chatbot interface and an API for third-parties using the chatbot. Chainlit also logs interactions with the chatbot to the LiteralAI evaluation platform.
   - LiteLLM provides a vendor-agnostic mechanism for accessing LLMs via an API.
 - The application uses AWS Aurora Serverless v2 as its database in deployed environments and Postgres when run locally. The application uses SQLAlchemy as an ORM, and the schema is controlled with Alembic and Pydantic. Model definitions are located in [app/src/db/models](https://github.com/navapbc/labs-decision-support-tool/tree/main/app/src/db/models).
   - The pgvector extension is used to provide a `vector` type, used for semantic search and document retrieval.
 - Policy documentation is scraped, parsed, and added to the database via [ingest_runner.py](https://github.com/navapbc/labs-decision-support-tool/tree/main/app/src/ingest_runner.py), which uses Scrapy, Playwright, and Beautiful Soup to parse online documentation. We use a custom parsing pipeline that intelligently splits documentation into semantically-meaningful chunks of content via an approach we call "tree-based chunking", implemented in [ingester.py](https://github.com/navapbc/labs-decision-support-tool/tree/main/app/src/ingester.py).
 - Evaluation code for e.g., automatically measuring the performance of the retrieval pipeline can be found in [/app/notebooks/metrics](https://github.com/navapbc/labs-decision-support-tool/tree/main/app/notebooks/metrics).
 - Additional investigative and exploratory code can be found in [/app/notebooks](https://github.com/navapbc/labs-decision-support-tool/tree/main/app/notebooks).

## Set up and run the application

To set up your local development environment, follow the instructions in [Getting Started](docs/app/getting-started.md).

### Managing the chatbot's data

To learn more about how to add additional data (or refresh existing data) in the chatbot, see [Data Management](docs/data-management.md).

## Research and evaluation

The chatbot has a few special commands built in to support research and evaluation. To learn more about batch processing and how to export user interaction logs, see [Special Commands](docs/special-commands.md).

## Deploying the application

The pilot instance of the chatbot has two environments, `DEV` and `PROD`.

Dev is a CD environment; merges to `main` automatically trigger deploys.

Prod requires a manual deploy step:
 1. On the [Releases page](https://github.com/navapbc/labs-decision-support-tool/releases), select `Draft a new release`
 1. Under `Choose a tag`, create a new tag, bumping the version number as appropriate (e.g., `v1.4.0` if the previous version was `v1.3.0`)
 1. Select `Generate release notes` to pre-populate the rest of the form. Adjust the notes as needed
 1. Click `Publish release` 
 1. [Select the Deploy App GitHub Action](https://github.com/navapbc/labs-decision-support-tool/actions/workflows/cd-app.yml)
 1. Under `Environment to deploy to`, select `prod`
 1. Under `Tag or branch or SHA to deploy`, enter the tag you created (e.g., `v1.4.0`)
 1. Click `Run workflow` (do not change `Use workflow from`)
