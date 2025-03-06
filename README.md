# Nava Labs Decision Support Tool

Welcome! You are at the root of the Nava Labs Decision Support Tool pilot repo.

## Local Development

To set up your local development environment, follow the instructions in [Getting Started](docs/app/getting-started.md).

## Data Ingestion

Chat engines (defined in [app/src/chat_engine.py](https://github.com/navapbc/labs-decision-support-tool/blob/main/app/src/chat_engine.py)) are downstream consumers of data sources. To add a new engine, a class must be created with the following attributes: `engine_id`, `name`, `datasets` (which must match the name of the ingestion dataset's script, see below), and a `formatting_config` which determines how the chat engine's response is formatted.
The `engine_id` determines the endpoint of the chatbot, while the `datasets` list points to the data sources to be consumed by the engine.

## Loading documents

The application supports using data from various sources including web scraping, JSON files, and PDFs. We have automated scripts for scraping and ingesting data from several sources.

The `./refresh-ingestion.sh` script automates most of the scraping and ingestion process for all data sources. This is the recommended approach for refreshing data. The following subsections first describe how to use this script, then detail each step performed by the script in case you want to run them individually.

### Refreshing all data sources

To refresh all data sources at once, use the refresh-ingestion.sh script from within `/app`:

```bash
./refresh-ingestion.sh all
```

This will scrape and ingest data from all supported sources except for 'ssa' (which requires manual scraping). The script only modifies the local database. To update the database in the respective deployment environments, the script generates 2 other scripts in the top-level directory: `refresh-dev-*.sh` and `refresh-prod-*.sh`, which should be reviewed before running.

Note that for the imagine_la dataset, you'll need to set the CONTENTHUB_PASSWORD environment variable:

```bash
export CONTENTHUB_PASSWORD="your_password_here"
./refresh-ingestion.sh all
```

### Refreshing specific data sources

To refresh a specific data source, specify the dataset ID:

```bash
./refresh-ingestion.sh ca_ftb
```

For the imagine_la dataset:

```bash
CONTENTHUB_PASSWORD="your_password_here" ./refresh-ingestion.sh imagine_la
```

Available datasets include: imagine_la, ca_ftb, ca_public_charge, ca_wic, covered_ca, irs, edd, la_policy, and ssa.

### Manual Process: Individual Steps

The following sections describe each step performed by the refresh-ingestion.sh script in case you want to run them individually.

### Web scraping

The refresh-ingestion.sh script handles both scraping and ingestion. For manual scraping:

```bash
make scrapy-runner args="dataset_id --debug"
```

For the imagine_la dataset:

```bash
make scrape-imagine-la CONTENTHUB_PASSWORD=your_password_here
```

For la_policy, which requires dynamic content scraping:

```bash
make scrape-la-county-policy
make scrapy-runner args="la_policy --debug"
```

### Loading documents locally

For manual ingestion, you can use the make commands directly:

```bash
make ingest-imagine-la DATASET_ID="Benefits Information Hub" BENEFIT_PROGRAM=mixed BENEFIT_REGION=California FILEPATH=src/ingestion/imagine_la/scrape/pages
```

```bash
make ingest-runner args="edd --json_input=src/ingestion/edd_scrapings.json"
```

Note that the DATASET_ID will be used in the chatbot web UI to prefix each citation, so use a user-friendly identifier like "CA EDD".

- The same `DATASET_ID` identifier can be used for multiple documents to represent that they belong in the same dataset.
- Example `BENEFIT_PROGRAM` values include `housing`, `utilities`, `food`, `medical`, `employment`, `SNAP`, `Medicaid`, etc.
- `BENEFIT_REGION` can correspond to a town, city, state, country, or any geographic area.

The Docker container mounts the `/app` folder, so FILEPATH should be relative to `/app`. `/app/documents` is ignored by git, so is a good place for files you want to load but not commit.

### Loading documents in a deployed environment

The refresh-ingestion.sh script generates deployment scripts for both dev and prod environments. After running the script, you'll find refresh-dev-YYYY-MM-DD.sh and refresh-prod-YYYY-MM-DD.sh in the top-level directory.

For manual deployment, the deployed application includes an S3 bucket, following the format `s3://decision-support-tool-app-<env>`, e.g., `s3://decision-support-tool-app-dev`.

After authenticating with AWS, from the root of this repo run:

```bash
aws s3 cp path/to/scrapings.json s3://decision-support-tool-app-dev/
./bin/run-command app <ENVIRONMENT> '["ingest-runner", "dataset_id", "--json_input", "s3://decision-support-tool-app-dev/scrapings.json"]'
```

Replace `<ENVIRONMENT>` with your environment, e.g., `dev`.

#### Resuming ingestion for large datasets

For large datasets like edd and la_policy, use the `--resume` flag to continue ingestion from where it last stopped:

```bash
./bin/run-command app <ENVIRONMENT> '["ingest-runner", "edd", "--json_input", "s3://decision-support-tool-app-dev/edd/edd_scrapings.json", "--resume"]'
```

This will commit the DB transaction for each Document, rather than committing after all Document records are added.

### To Skip Access to the DB

For dry-runs or exporting of markdown files, avoid reading and writing to the DB during ingestion by adding the `--skip_db` argument:

```bash
make ingest-runner args="dataset_id --json_input=path/to/scrapings.json --skip_db"
```

Or set the environment variable before running refresh-ingestion.sh:

```bash
export SKIP_LOCAL_EMBEDDING=true
./refresh-ingestion.sh dataset_id
```

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

## Backing up DB contents

Since the DB contents will be replaced upon reingestion, new UUIDs will be generated for reingested chunks and documents, which can make diagnosing problems challenging when logs refer to UUIDs that no longer exist in the DB. Before running `refresh-ingestion.sh`, it behooves us to create a backup of DB contents so we can reference the old UUIDs (after restoring the backup to a local DB).

To backup DB contents for the `dev` deployment, run `./bin/run-command app dev '["pg-dump", "backup"]'` to create a [PostgreSQL dump file](https://www.postgresql.org/docs/current/backup-dump.html) and upload it to the `pg_dumps` folder in S3. For the `prod` environment, replace `dev` with `prod`.

### Restoring DB contents locally

To restore the DB contents locally, run `make pg-dump args="restore --dumpfile db.dump"`, replacing `db.dump` with the file downloaded from S3. Run `make pg-dump args="--help"` for more options.
