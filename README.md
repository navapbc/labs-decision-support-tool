# Nava Labs Decision Support Tool

Welcome! You are at the root of the Nava Labs Decision Support Tool pilot repo. This repo contains code for a chatbot that answers questions about public benefit programs. It is powered by generative AI and retrieval-augmented-generation ("RAG") and intended for use by benefit navigators that have prior experience and familiarity with these programs.

## Project description

The chatbot ingests and parses documentation on policy programs, and then searches across this database of documentation to inform its responses. In March 2025, Nava began a pilot of this chatbot in partnership with [Imagine LA](https://www.imaginela.org/). Users of Imagine LA's [Benefit Navigator](https://www.imaginela.org/benefit-navigator) were provided access to a chatbot with access to documentation about CalWorks, CalFresh, Med-Cal, various tax credits and housing assistance programs, unemployment insurance, state disability insurance, paid family leave, and more.

## Project components

This project is built on Nava's open source [infrastructure template](https://github.com/navapbc/template-infra) and [Python application template](https://github.com/navapbc/template-application-flask/), part of [Nava's Platform](https://github.com/navapbc/platform).

 - The application is hosted in AWS, and the infrastructure is defined via Terraform in [/infra](https://github.com/navapbc/labs-decision-support-tool/tree/main/infra).
 - The application code is written in Python and is located in [/app/src](https://github.com/navapbc/labs-decision-support-tool/tree/main/app/src).
   - Chainlit and FastAPI are used to provide a chatbot interface and an API for third-parties using the chatbot. Chainlit also logs interactions with the chatbot to the Literal evaluation platform.
   - LiteLLM provides a vendor-agnostic mechanism for accessing LLMs via an API.
 - The application uses AWS Aurora Serverless v2 as its database in deployed environments and Postgres when run locally. The application uses SQLAlchemy as an ORM, and the schema is controlled with Alembic and Pydantic. Model defintions are located in [app/src/db/models](https://github.com/navapbc/labs-decision-support-tool/tree/main/app/src/db/models).
   - The pgvector extension is used to provide a `vector` type, used for semantic search and document retrieval.
- Evaluation code for e.g., automatically measuring the performance of the retrieval pipeline can be found in [/app/notebooks/metrics](https://github.com/navapbc/labs-decision-support-tool/tree/main/app/notebooks/metrics).
- Additional investigative and exploratory code can be found in [/app/notebooks](https://github.com/navapbc/labs-decision-support-tool/tree/main/app/notebooks).

## Set up and run the application

To set up your local development environment, follow the instructions in [Getting Started](docs/app/getting-started.md).

### Managing the chatbot's data

To learn more about how to add additional data (or refresh existing data) in the chatbot, see [Data Management](docs/data-management.md).