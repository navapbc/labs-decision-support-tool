import asyncio
import csv
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor

from src.chat_engine import ChatEngineInterface
from src.citations import simplify_citation_numbers
from src.util.file_util import convert_to_utf8

logger = logging.getLogger(__name__)


async def batch_process(file_path: str, engine: ChatEngineInterface) -> str:

    # Convert file contents to clean UTF-8
    content = convert_to_utf8(file_path)

    reader = csv.DictReader(content.splitlines())

    if not reader.fieldnames or "question" not in reader.fieldnames:
        raise ValueError("CSV file must contain a 'question' column.")

    rows = list(reader)  # Convert reader to list to preserve order
    questions = [row["question"] for row in rows]

    # Follow example usage https://docs.python.org/3/library/concurrent.futures.html#threadpoolexecutor-example
    with ThreadPoolExecutor() as executor:
        # Process questions in parallel while preserving order
        futures = [
            executor.submit(_process_question, i, q, engine)
            for i, q in enumerate(questions, start=1)
        ]
        logger.info("Submitted %i questions for processing", len(futures))

        def update_rows() -> None:
            logger.info("Waiting for results...")
            # Update rows with processed data while preserving original order
            for row, f in zip(rows, futures, strict=True):
                row.update(f.result())  # f.result() is a blocking call
            logger.info("Updated %i rows", len(rows))

        # Waiting for results is blocking so run_in_executor
        # https://docs.python.org/3/library/asyncio-eventloop.html#executing-code-in-thread-or-process-pools
        await asyncio.get_running_loop().run_in_executor(executor, update_rows)

    # Update fieldnames to include new columns
    all_row_fieldnames = list(reader.fieldnames) + [key for p in rows for key in p.keys()]
    # Use dict.keys() to get an ordered set of fieldnames
    all_fieldnames = list({f: None for f in all_row_fieldnames}.keys())
    logger.info("all_fieldnames: %r", all_fieldnames)

    result_file = tempfile.NamedTemporaryFile(delete=False, mode="w", newline="", encoding="utf-8")
    logger.info("Writing results to file %r", result_file.name)

    writer = csv.DictWriter(result_file, fieldnames=all_fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    result_file.close()

    return result_file.name


def _process_question(
    index: int, question: str, engine: ChatEngineInterface
) -> dict[str, str | None]:
    try:
        logger.info("Processing question %i: %s...", index, question[:50])
        result = engine.on_message(question=question, chat_history=[])
        final_result = simplify_citation_numbers(result)

        result_table: dict[str, str | None] = {"answer": final_result.response}

        for subsection in final_result.subsections:
            citation_key = "citation_" + subsection.id
            formatted_headings = (
                " > ".join(subsection.text_headings) if subsection.text_headings else ""
            )
            result_table |= {
                citation_key + "_name": subsection.chunk.document.name,
                citation_key + "_headings": formatted_headings,
                citation_key + "_source": subsection.chunk.document.source,
                citation_key + "_text": subsection.text,
            }

        logger.info("Question %i processed with %d citations", index, len(final_result.subsections))
        return result_table
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error processing question %i: %s", index, e, stack_info=True)
        return {"answer": f"Error processing question: {str(e)}"}
