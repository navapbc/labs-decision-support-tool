import asyncio
import csv
import gc
import logging
import tempfile
from typing import Awaitable, Callable, Optional

from src.chat_engine import ChatEngineInterface
from src.citations import simplify_citation_numbers

logger = logging.getLogger(__name__)


async def batch_process(
    file_path: str,
    engine: ChatEngineInterface,
    progress_callback: Optional[Callable[[int, int], Awaitable[None]]] = None,
) -> str:
    """
    Process a batch of questions from a CSV file.

    Args:
        file_path: Path to input CSV file
        engine: Chat engine instance to use
        progress_callback: Optional callback for progress updates

    Returns:
        Path to results file
    """
    logger.info("Starting batch processing of file: %r", file_path)

    with open(file_path, mode="r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)

        if not reader.fieldnames or "question" not in reader.fieldnames:
            logger.error("Invalid CSV format: missing 'question' column in %r", file_path)
            raise ValueError("CSV file must contain a 'question' column.")

        rows = list(reader)
        questions = [row["question"] for row in rows]
        total_questions = len(questions)
        logger.info("Found %d questions to process", total_questions)

        processed_data = []

        # Process in smaller batches to manage memory
        BATCH_SIZE = 10
        for i, q in enumerate(questions, 1):
            logger.info("Processing question %d/%d", i, total_questions)

            if progress_callback:
                await progress_callback(i, total_questions)

            processed_data.append(_process_question(q, engine))

            # Clear memory after each batch
            if i % BATCH_SIZE == 0:
                # Add small delay to prevent overwhelming the system
                await asyncio.sleep(0.1)
                # Force garbage collection to free memory
                gc.collect()

        # Update rows with processed data
        for row, data in zip(rows, processed_data, strict=True):
            row.update(data)

        # Prepare output file
        all_fieldnames = list(
            {
                f: None
                for f in list(reader.fieldnames) + [key for p in processed_data for key in p.keys()]
            }.keys()
        )

        result_file = tempfile.NamedTemporaryFile(
            delete=False, mode="w", newline="", encoding="utf-8", suffix=".csv"
        )

        writer = csv.DictWriter(result_file, fieldnames=all_fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        result_file.close()

        logger.info("Batch processing complete. Results written to: %r", result_file.name)
        return result_file.name


import time
def _process_question(question: str, engine: ChatEngineInterface) -> dict[str, str | None]:
    logger.debug("Processing question: %r", question)
    if True:
        from src.citations import ResponseWithSubsections
        from src.db.models.document import Chunk, Document, Subsection

        document = Document(name="dummy document", source="dummy source")
        final_result = ResponseWithSubsections(
            "dummy response",
            [
                Subsection(
                    "1", Chunk(content="markdown", document=document, headings=["headings"]), ""
                )
            ],
        )
        time.sleep(15)
    else:
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

    logger.debug("Question processed with %d citations", len(final_result.subsections))
    return result_table
