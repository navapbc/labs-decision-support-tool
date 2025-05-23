#!/bin/bash

# This ingestion process is different the others
ingest_imagine_la() {
    local DATASET_ID=imagine_la
    check_preconditions "$DATASET_ID"

    # Move previous scraped html files if it's not from today
    if [ -d "src/ingestion/imagine_la/pages" ] && ! [ -d "src/ingestion/imagine_la/pages-$TODAY" ]; then
        echo "Clearing scraped html files"
        mv -iv "src/ingestion/imagine_la/pages"{,-$TODAY}
    else
        echo "Using scraped html files created today"
    fi

    [ -n "$CONTENT_HUB_SPACE_ID" ] || { echo "CONTENT_HUB_SPACE_ID is not set!"; exit 31; }
    [ -n "$CONTENT_HUB_ACCESS_TOKEN" ] || { echo "CONTENT_HUB_ACCESS_TOKEN is not set!"; exit 31; }
    
    # Scrape the website
    make scrape-imagine-la 2>&1 | tee logs/${DATASET_ID}-1scrape.log
    if grep -E 'make:.*Error|log_count/ERROR' "logs/${DATASET_ID}-1scrape.log"; then
        echo "ERROR: Scraping failed. Check logs/${DATASET_ID}-1scrape.log"
        exit 33
    fi

    # Move any previous markdown files
    [ -d "${DATASET_ID}_md" ] && mv -iv "$DATASET_ID"{,-orig}_md

    if [ -z "$SKIP_LOCAL_INGEST" ]; then
        # Save markdown files and ingest into DB
        make ingest-imagine-la DATASET_ID="Benefits Information Hub" BENEFIT_PROGRAM=mixed BENEFIT_REGION=California \
            FILEPATH=src/ingestion/imagine_la/pages 2>&1 | tee logs/${DATASET_ID}-2ingest.log
        if [ $? -ne 0 ] || grep -E 'make:.*Error' "logs/${DATASET_ID}-2ingest.log"; then
            echo "ERROR: ingest-runner failed. Check logs/${DATASET_ID}-2ingest.log"
            exit 32
        fi
    fi

    create_md_zip "$DATASET_ID"

    echo "=== Copy the following to Slack ==="
    echo_stats "$DATASET_ID"

    echo "REMINDERS:"
    echo_cmds "$DATASET_ID"
}

scrape_and_ingest() {
    local DATASET_ID="$1"
    check_preconditions "$DATASET_ID"

    if [ "$DATASET_ID" = "la_policy" ]; then
        # Use playwright to scrape dynamic content
        make scrape-la-county-policy 2>&1 | tee "logs/${DATASET_ID}-0playwright-scrape.log"
    fi

    # Clear out the Scrapy cache if it's not from today
    if [ -d "src/ingestion/.scrapy/httpcache/${DATASET_ID}_spider" ] && ! [ -d "src/ingestion/.scrapy/httpcache/${DATASET_ID}_spider-$TODAY" ]; then
        echo "Clearing Scrapy cache"
        mv -iv "src/ingestion/.scrapy/httpcache/${DATASET_ID}_spider"{,-$TODAY}
    fi

    if ! [ "$DATASET_ID" = "ssa" ]; then
        echo "Using Scrapy cache created today"
        # Run Scrapy on html files to create markdown in JSON file
        make scrapy-runner args="$DATASET_ID --debug" 2>&1 | tee "logs/${DATASET_ID}-1scrape.log"
        if grep -E 'make:.*Error|log_count/ERROR' "logs/${DATASET_ID}-1scrape.log"; then
            echo "ERROR: Scrapy failed. Check logs/${DATASET_ID}-1scrape.log"
            exit 21
        fi
    fi

    # Move any previous markdown files
    [ -d "${DATASET_ID}_md" ] && mv -iv "$DATASET_ID"{,-orig}_md

    if [ "$SKIP_LOCAL_EMBEDDING" = "true" ]; then
        EXTRA_INGEST_ARGS="$EXTRA_INGEST_ARGS --skip_db"
    fi

    # Save markdown files and ingest into DB
    make ingest-runner args="$DATASET_ID $EXTRA_INGEST_ARGS" 2>&1 | tee "logs/${DATASET_ID}-2ingest.log"
    if [ $? -ne 0 ] || grep -E 'make:.*Error' "logs/${DATASET_ID}-2ingest.log"; then
        echo "ERROR: ingest-runner failed. Check logs/${DATASET_ID}-2ingest.log"
        exit 22
    fi

    create_md_zip "$DATASET_ID"

    echo "=== Copy the following to Slack ==="
    echo_stats "$DATASET_ID"

    echo "REMINDERS:"
    echo_cmds "$DATASET_ID"
}

create_md_zip(){
    local DATASET_ID="$1"
    [ -d "${DATASET_ID}_md" ] || exit 29

    # Collect stats before zipping
    collect_stats "$DATASET_ID"

    # Include stats.json in the zip along with other logs
    zip "${DATASET_ID}_md.zip" -r "${DATASET_ID}_md" logs/"$DATASET_ID"*.log logs/"$DATASET_ID"*.json
    mv -iv "${DATASET_ID}_md" "${DATASET_ID}-${TODAY}_md"
}

collect_stats(){
    local DATASET_ID="$1"

    local MARKDOWN_COUNT=$(find "${DATASET_ID}_md" -type f -iname '*.md' | wc -l)
    local INGEST_STATS=$(grep -E "Running with args|DONE splitting|Finished ingesting" "logs/${DATASET_ID}-2ingest.log")
    local SCRAPE_STATS=$(grep -E 'log_count|item_scraped_count|request_depth|downloader/|httpcache/' "logs/${DATASET_ID}-1scrape.log")
    local HTML_COUNT=0
    if [ -d "src/ingestion/imagine_la/pages" ]; then
        HTML_COUNT=$(ls src/ingestion/imagine_la/pages | wc -l)
    fi

    # Parse ingest stats
    local PAGES_COUNT=$(echo "$INGEST_STATS" | grep "DONE splitting" | sed -E 's/.*splitting all ([0-9]+) webpages.*/\1/')
    local CHUNKS_COUNT=$(echo "$INGEST_STATS" | grep "DONE splitting" | sed -E 's/.*total of ([0-9]+) chunks.*/\1/')
    local INGEST_STATUS=$(echo "$INGEST_STATS" | grep -q "Finished ingesting" && echo "completed" || echo "failed")
    
    # Parse scrape stats into key-value pairs
    local SCRAPE_PARSED=$(echo "$SCRAPE_STATS" | sed 's/{//g; s/}//g; s/'"'"'//g' | tr -d '\n' | sed 's/: /:/g' | tr ',' '\n' | while read -r line; do
        key=$(echo "$line" | cut -d':' -f1 | tr -d ' ')
        value=$(echo "$line" | cut -d':' -f2 | tr -d ' ')
        if [ ! -z "$key" ]; then
            echo "            \"$key\": $value,"
        fi
    done | sed '$ s/,$//')

    # Save stats to JSON
    cat > "logs/${DATASET_ID}-${TODAY}_stats_raw.json" << EOF
{
    "dataset_id": "$DATASET_ID",
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "stats": {
        "markdown_files": $MARKDOWN_COUNT,
        "html_files": $HTML_COUNT,
        "ingest": {
            "chunks_split": {
                "pages": ${PAGES_COUNT:-0},
                "chunks": ${CHUNKS_COUNT:-0}
            },
            "status": "$INGEST_STATUS"
        },
        "scrape": {
$SCRAPE_PARSED
        }
    }
}
EOF

    # Validate and pretty-print the JSON
    if command -v jq >/dev/null 2>&1; then
        jq '.' "logs/${DATASET_ID}-${TODAY}_stats_raw.json" > "logs/${DATASET_ID}-${TODAY}_stats.json" && \
        rm -v "logs/${DATASET_ID}-${TODAY}_stats_raw.json"
    fi
}

echo_stats(){
    local DATASET_ID="$1"
    echo "------ $DATASET_ID ----------------"
    if [ "$DATASET_ID" == "imagine_la" ]; then
        ls -ld src/ingestion/imagine_la/pages
        echo "HTML files scraped: "
        ls src/ingestion/imagine_la/pages | wc -l
    else
        grep -E 'log_count|item_scraped_count|request_depth|downloader/|httpcache/' "logs/${DATASET_ID}-1scrape.log"
    fi
    grep -E "Running with args|DONE splitting|Finished ingesting" "logs/${DATASET_ID}-2ingest.log"
    ls -ld "${DATASET_ID}-${TODAY}_md"
    echo "Markdown file count: $(find "${DATASET_ID}-${TODAY}_md" -type f -iname '*.md' | wc -l)"
    echo "-----------------------------------"
}

echo_cmds(){
    local DATASET_ID="$1"
    echo "# 1. Upload the zip file to the 'Chatbot Knowledge Markdown' Google Drive folder, replacing the old zip file."
    echo "   $(ls -l "${DATASET_ID}_md.zip")"
    echo ""
    echo "# 2. Review and run the ingestion script to update deployment: (cd .. && sh ./refresh-${DEPLOY_ENV}-${TODAY}.sh >> refresh-${DEPLOY_ENV}-${TODAY}.log) "

    local REFRESH_SH="../refresh-${DEPLOY_ENV}-${TODAY}.sh"
    if ! [ -e "$REFRESH_SH" ]; then
        {
            echo "#!/bin/sh"
            echo "set -o errexit"
            echo "./bin/terraform-init infra/app/service $DEPLOY_ENV"
            echo ""
        } > $REFRESH_SH
        chmod +x $REFRESH_SH
    else
        echo "" >> $REFRESH_SH
    fi

    if [ "$DATASET_ID" == "imagine_la" ]; then
        {
        echo "# $DATASET_ID: Upload to S3"
        local S3_HTML_DIR="s3://decision-support-tool-app-${DEPLOY_ENV}/imagine_la-${TODAY}"
        echo "aws s3 sync \"app/src/ingestion/imagine_la/pages/\" \"$S3_HTML_DIR/\""
        echo "aws s3 cp \"app/logs/${DATASET_ID}-${TODAY}_stats.json\" \"${S3_HTML_DIR}/stats/${TODAY}_stats.json\""

        echo "# $DATASET_ID: Ingest"
        local S3_HTML_DIR="s3://decision-support-tool-app-${DEPLOY_ENV}/imagine_la-${TODAY}"
        echo "./bin/run-command app ${DEPLOY_ENV} '[\"ingest-imagine-la\", \"Benefits Information Hub\", \"mixed\", \"California\", \"$S3_HTML_DIR\"]' &> ${DEPLOY_ENV}-task-${DATASET_ID}.log &"
        echo "sleep 5"
        } >> $REFRESH_SH
    elif [ "$DATASET_ID" == "ssa" ]; then
        {
        echo "# $DATASET_ID: Upload to S3"
        echo "# $DATASET_ID was manually scraped"
        local S3_DIR="s3://decision-support-tool-app-${DEPLOY_ENV}/${DATASET_ID}"
        local S3_SCRAPINGS_FILE="${S3_DIR}/ssa_scrapings.json"
        echo "Assuming files are directly under the app/ folder"
        echo "aws s3 cp app/ssa_scrapings.json ${S3_SCRAPINGS_FILE}"
        echo "aws s3 sync app/ssa_extra_md ${S3_DIR}/ssa_extra_md"
        echo "# $DATASET_ID: Ingest"
        echo "./bin/run-command app ${DEPLOY_ENV} '[\"ingest-runner\", \"ssa\", \"--json_input\", \"${S3_SCRAPINGS_FILE}\"]' &> ${DEPLOY_ENV}-task-${DATASET_ID}.log &"
        echo "sleep 5"
        } >> $REFRESH_SH
    else
        {
        echo "# $DATASET_ID: Upload to S3"
        local S3_DIR="s3://decision-support-tool-app-${DEPLOY_ENV}/${DATASET_ID}"
        local S3_SCRAPINGS_FILE="${S3_DIR}/${DATASET_ID}_scrapings-${TODAY}.json"
        echo "aws s3 cp \"app/src/ingestion/${DATASET_ID}_scrapings.json\" \"$S3_SCRAPINGS_FILE\""
        echo "aws s3 cp \"app/logs/${DATASET_ID}-${TODAY}_stats.json\" \"${S3_DIR}/stats/${TODAY}_stats.json\""

        echo "# $DATASET_ID: Ingest"
        local S3_DIR="s3://decision-support-tool-app-${DEPLOY_ENV}/${DATASET_ID}"
        local S3_SCRAPINGS_FILE="${S3_DIR}/${DATASET_ID}_scrapings-${TODAY}.json"
        if [ "$DATASET_ID" == "edd" ] || [ "$DATASET_ID" == "la_policy" ]; then
            echo "{"
            echo "#   Dropping table first so ingestion can use --resume in subsequent runs"
            echo "./bin/run-command app $DEPLOY_ENV '[\"ingest-runner\", \"$DATASET_ID\", \"--drop-only\"]'"
            echo "#   Ingest with --resume since it's a large dataset and can fail due to resource limits"
            echo "date"
            echo "while ! ./bin/run-command app $DEPLOY_ENV '[\"ingest-runner\", \"$DATASET_ID\", \"--json_input\", \"$S3_SCRAPINGS_FILE\", \"--resume\"]'; do"
            echo "   date"
            echo "   echo \"Resuming/retrying ...\""
            echo "done"
            echo "} &> ${DEPLOY_ENV}-task-${DATASET_ID}.log &"
        else
            echo "./bin/run-command app $DEPLOY_ENV '[\"ingest-runner\", \"$DATASET_ID\", \"--json_input\", \"$S3_SCRAPINGS_FILE\"]' &> ${DEPLOY_ENV}-task-${DATASET_ID}.log &"
        fi
        echo "sleep 5"
        } >> $REFRESH_SH
    fi
}

check_preconditions(){
    local ERROR
    for F in "$1-${TODAY}_md" "$1-orig_md" "${DATASET_ID}_md.zip"; do
        if [ -e "$F" ]; then
            echo "ERROR: $F already exists!"
            ERROR=1
        fi
    done
    if [ "$ERROR" == "1" ]; then
        echo "Move or delete the file/folder(s) before running this script."
        exit 50
    fi
}

poll_until_finished() {
    pushd ..
    local PREFIX="$1-task"

    echo ""
    echo "## Completed:"
    for L in $(grep -e "INFO - Finished ingesting" -l ${PREFIX}-*.log); do
        echo ""
        echo "$L:"
        grep -E '(INFO - Ingesting from|INFO - Finished ingesting)' $L
    done

    local INCOMPLETE_TASKS="$(grep -e "INFO - Finished ingesting" -L ${PREFIX}-*.log)"
    while [ "$INCOMPLETE_TASKS" ]; do
        echo ""
        echo "## Waiting for incomplete tasks:"
        for L in $INCOMPLETE_TASKS; do
            echo ""
            echo "$L:"
            tail -n 4 "$L"
        done
        sleep 60
        INCOMPLETE_TASKS="$(grep -e "INFO - Finished ingesting" -L ${PREFIX}-*.log)"
    done

    for L in $(grep -e "INFO - Finished ingesting" -l ${PREFIX}-*.log); do
        echo ""
        echo "$L:"
        grep -E '(INFO - Ingesting from|INFO - Finished ingesting)' $L
    done
    popd
}

if ! [ -e "refresh-ingestion.sh" ]; then
    echo "ERROR: Run this script from the 'app' directory."
    exit 10
fi
if [ -z "$1" ]; then
    echo "Usage: '$0 <DATASET_ID>', where <DATASET_ID> is any of the following:"
    echo -n "  imagine_la"
    grep "case" src/ingest_runner.py | tr '":' ' ' | while read CASE DATASET_ID COLON; do [ "$DATASET_ID" != "_" ] && echo -n ", $DATASET_ID"; done
    echo ""
    echo "If <DATASET_ID> is 'all', it will run re-scrape all the datasets and create scripts for both dev and prod."
    echo "  SKIP_LOCAL_EMBEDDING=true by default when <DATASET_ID>='all'."
    echo "Set DEPLOY_ENV to 'dev' (default) or 'prod' to create refresh-$DEPLOY_ENV.sh script for the appropriate environment."
    echo "Set SKIP_LOCAL_INGEST=true to skip local ingestion but still create files for upload and ingestion for the deployed app."
    echo "Set TODAY=YYYY-MM-DD to use a different date than the current day."
    exit 1
fi

# Function to handle the exit signal
handle_exit() {
  exit_code=$?
  if [ $exit_code -ne 0 ]; then
    echo "Error: Script exited with code $exit_code" >&2
  fi
}
# Trap the EXIT signal and call the handle_exit function
trap handle_exit EXIT

mkdir -p logs
: ${TODAY:=$(date "+%Y-%m-%d")}
: ${DEPLOY_ENV:=dev}
echo "Using TODAY=$TODAY DEPLOY_ENV=$DEPLOY_ENV"

case "$1" in
    imagine_la)
        ingest_imagine_la
        ;;
    ssa)
        if ! [ -e "ssa_scrapings.json" ] || ! [ -d "ssa_extra_md" ]; then
            echo "ERROR: ssa_scrapings.json and ssa_extra_md/ folder are missing."
            echo "Download them from https://us-east-1.console.aws.amazon.com/s3/buckets/decision-support-tool-app-${DEPLOY_ENV}?region=us-east-1&bucketType=general&prefix=ssa/"
            exit 2
        fi
        EXTRA_INGEST_ARGS="--json_input=ssa_scrapings.json"
        scrape_and_ingest "$1"
        ;;
    cmds)
        if [ -z "$2" ]; then
            echo "Usage: '$0 cmds <DATASET_ID>'"
            exit 3
        fi
        echo_cmds "$2"
        ;;
    stats)
        if [ -z "$2" ]; then
            echo "Usage: '$0 stats <DATASET_ID>'"
            exit 3
        fi
        echo_stats "$2"
        ;;
    all)
        mkdir -p OLD_INGESTION-$TODAY
        mv -v *.zip *_md OLD_INGESTION-$TODAY/

        # Don't need to update embeddings locally when refreshing deployed app
        # Skipping creating local embeddings saves time
        : ${SKIP_LOCAL_EMBEDDING:=true}
        export DEPLOY_ENV=dev

        # Skip 'ssa' dataset since it was manually scraped and hence needs to be refreshed manually
        DATASETS="ca_ftb ca_public_charge ca_wic covered_ca irs edd la_policy"

        for DATASET_ID in $DATASETS; do
            scrape_and_ingest "$DATASET_ID"
        done
        ingest_imagine_la

        # The prior commands created a refresh script for dev
        # The following quickly creates a refresh script for prod
        export DEPLOY_ENV=prod
        for DATASET_ID in $DATASETS imagine_la; do
            echo_cmds "$DATASET_ID"
        done

        echo "=== Copy the following to Slack and compare counts with previous reingestions ==="
        for DATASET_ID in $DATASETS imagine_la; do
            echo_stats "$DATASET_ID"
        done

        echo ""
        echo "REMINDERS:"
        echo "- Upload the zip files to the ['Chatbot Knowledge Markdown' Google Drive folder](https://drive.google.com/drive/folders/1ZLWC2HdWKqprvIcd_6Y_M_ekJmABeONk)."
        echo "- Review and run the refresh scripts (in the top-level folder): refresh-dev-${TODAY} and refresh-prod-${TODAY}."
        echo "- Check ingestion status and wait for completion: DEPLOY_ENV=prod ./refresh-ingestion.sh wait_until_done"
        echo "- Restore local TF to dev environment: ./bin/terraform-init infra/app/service dev"
        ;;
    wait_until_done)
        poll_until_finished "$DEPLOY_ENV"
        ;;
    *)
        scrape_and_ingest "$1"
        ;;
esac
