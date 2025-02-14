#!/bin/bash

# This ingestion process is different the others
ingest_imagine_la() {
    local DATASET_ID=imagine_la
    check_preconditions "$DATASET_ID"

    # Move previous scraped html files if it's not from today
    if [ -d "src/ingestion/imagine_la/scrape/pages" ] && ! [ -d "src/ingestion/imagine_la/scrape/pages-$TODAY" ]; then
        echo "Clearing scraped html files"
        mv -iv "src/ingestion/imagine_la/scrape/pages"{,-$TODAY}
    else
        echo "Using scraped html files created today"
    fi

    [ "$CONTENTHUB_PASSWORD" ] || { echo "CONTENTHUB_PASSWORD is not set!"; exit 31; }
    # Scrape the website
    make scrape-imagine-la CONTENTHUB_PASSWORD=$CONTENTHUB_PASSWORD 2>&1 | tee logs/${DATASET_ID}-1scrape.log

    # Move any previous markdown files
    [ -d "${DATASET_ID}_md" ] && mv -iv "$DATASET_ID"{,-orig}_md

    # Save markdown files and ingest into DB
    make ingest-imagine-la DATASET_ID="Imagine LA" BENEFIT_PROGRAM=mixed BENEFIT_REGION=California \
        FILEPATH=src/ingestion/imagine_la/scrape/pages 2>&1 | tee logs/${DATASET_ID}-2ingest.log
    if [ $? -ne 0 ] || grep -E 'make:.*Error' "logs/${DATASET_ID}-2ingest.log"; then
        echo "ERROR: ingest-runner failed. Check logs/${DATASET_ID}-2ingest.log"
        exit 32
    fi

    create_md_zip "$DATASET_ID"

    echo "-----------------------------------"
    echo "=== Copy the following to Slack ==="
    ls -ld src/ingestion/imagine_la/scrape/pages
    echo "HTML files scraped: "
    ls src/ingestion/imagine_la/scrape/pages | wc -l
    echo_stats "$DATASET_ID"
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
    else
        echo "Using Scrapy cache created today"
    fi

    if ! [ "$DATASET_ID" = "ssa" ]; then
        # Run Scrapy on html files to create markdown in JSON file
        make scrapy-runner args="$DATASET_ID --debug" 2>&1 | tee "logs/${DATASET_ID}-1scrape.log"
        if grep -E 'make:.*Error|log_count/ERROR' "logs/${DATASET_ID}-1scrape.log"; then
            echo "ERROR: Scrapy failed. Check logs/${DATASET_ID}-1scrape.log"
            exit 21
        fi
    fi

    # Move any previous markdown files
    [ -d "${DATASET_ID}_md" ] && mv -iv "$DATASET_ID"{,-orig}_md

    # Save markdown files and ingest into DB
    make ingest-runner args="$DATASET_ID $EXTRA_INGEST_ARGS" 2>&1 | tee "logs/${DATASET_ID}-2ingest.log"
    if [ $? -ne 0 ] || grep -E 'make:.*Error' "logs/${DATASET_ID}-2ingest.log"; then
        echo "ERROR: ingest-runner failed. Check logs/${DATASET_ID}-2ingest.log"
        exit 22
    fi

    if [ "$DATASET_ID" = "edd" ]; then
        while grep "NotImplementedError: TableRow node" "logs/${DATASET_ID}-2ingest.log"; do
            echo "Manually fix error: Edit src/ingestion/edd_scrapings.json (see edd_md/jobs_and_training/Layoff_Services_WARN/_index.md for reference)"
            echo "by converting the last table row starting with 'Exceptions and Exemptions to Notice Requirements' into paragraphs by replacing '|' with '\\\n'."
            echo "After fixing, press Enter to retry ingestion."
            read OK
            make ingest-runner args="$DATASET_ID $EXTRA_INGEST_ARGS" 2>&1 | tee "logs/${DATASET_ID}-2ingest.log"
        done
    fi

    create_md_zip "$DATASET_ID"
}

create_md_zip(){
    local DATASET_ID="$1"
    [ -d "${DATASET_ID}_md" ] || exit 29

    # Collect stats before zipping
    local MARKDOWN_COUNT=$(find "${DATASET_ID}_md" -type f -iname '*.md' | wc -l)
    local INGEST_STATS=$(grep -E "Running with args|DONE splitting|Finished ingesting" "logs/${DATASET_ID}-2ingest.log")
    local SCRAPE_STATS=$(grep -E 'log_count|item_scraped_count|request_depth|downloader/|httpcache/' "logs/${DATASET_ID}-1scrape.log")
    local HTML_COUNT=0
    if [ -d "src/ingestion/imagine_la/scrape/pages" ]; then
        HTML_COUNT=$(ls src/ingestion/imagine_la/scrape/pages | wc -l)
    fi

    # Save stats to JSON
    cat > "logs/${DATASET_ID}-${TODAY}_stats.json" << EOF
{
    "dataset_id": "$DATASET_ID",
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "stats": {
        "markdown_files": $MARKDOWN_COUNT,
        "html_files": $HTML_COUNT,
        "ingest_log": $(echo "$INGEST_STATS" | jq -R -s -c 'split("\n")[:-1]'),
        "scrape_log": $(echo "$SCRAPE_STATS" | sed 's/{//g; s/}//g; s/'"'"'//g' | tr -d '\n' | sed 's/: /:/g' | jq -R -c 'split(", ")[:-1]')
    }
}
EOF

    echo "-----------------------------------"
    echo "=== Copy the following to Slack ==="
    grep -E 'log_count|item_scraped_count|request_depth|downloader/|httpcache/' "logs/${DATASET_ID}-1scrape.log"
    echo_stats "$DATASET_ID"

    # Include stats.json in the zip along with other logs
    zip "${DATASET_ID}_md.zip" -r "${DATASET_ID}_md" logs/"$DATASET_ID"*.log logs/"$DATASET_ID"*.json
    mv -iv "${DATASET_ID}_md" "${DATASET_ID}-${TODAY}_md"
}

echo_stats(){
    local DATASET_ID="$1"
    grep -E "Running with args|DONE splitting|Finished ingesting" "logs/${DATASET_ID}-2ingest.log"
    ls -ld "${DATASET_ID}-${TODAY}_md"
    echo "Markdown file count: $(find "${DATASET_ID}-${TODAY}_md" -type f -iname '*.md' | wc -l)"
    echo "-----------------------------------"
    echo "REMINDERS:"
    echo "1. Upload the zip file to the 'Chatbot Knowledge Markdown' Google Drive folder, replacing the old zip file."
    echo "   $(ls -l "${DATASET_ID}_md.zip")"
    echo "2. Upload ingester input files (e.g., *-scrapings.json) and stats to S3:"
    echo "   aws s3 sync src/ingestion s3://decision-support-tool-app-dev/${DATASET_ID}"
    echo "   aws s3 cp logs/${DATASET_ID}-${TODAY}_stats.json s3://decision-support-tool-app-dev/${DATASET_ID}/stats/${TODAY}_stats.json"
    echo "3. Run ingestion on deployed app:"
    echo "   ./bin/run-command app dev ..."
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
        exit 20
    fi
}

if [ -z "$1" ]; then
    echo "Usage: '$0 <DATASET_ID>', where <DATASET_ID> is any of the following:"
    echo -n "  imagine_la"
    grep "case" src/ingest_runner.py | tr '":' ' ' | while read CASE DATASET_ID COLON; do [ "$DATASET_ID" != "_" ] && echo -n ", $DATASET_ID"; done
    echo ""
    exit 1
fi

mkdir -p logs
export TODAY=$(date "+%Y-%m-%d")

case "$1" in
    imagine_la)
        ingest_imagine_la
        ;;
    ssa)
        if ! [ -e "ssa_scrapings.json" ] || ! [ -d "ssa_extra_md" ]; then
            echo "ERROR: ssa_scrapings.json and ssa_extra_md/ folder are missing."
            echo "Download them from https://us-east-1.console.aws.amazon.com/s3/buckets/decision-support-tool-app-dev?region=us-east-1&bucketType=general&prefix=ssa/"
            exit 2
        fi
        EXTRA_INGEST_ARGS="--json_input=ssa_scrapings.json"
        scrape_and_ingest "$1"
        ;;
    *)
        scrape_and_ingest "$1"
        ;;
esac
