import csv
import logging
import tempfile

import chainlit as cl
from src.chat_engine import ChatEngineInterface
from src.citations import simplify_citation_numbers

logger = logging.getLogger(__name__)


async def batch_process(file_path: str, engine: ChatEngineInterface) -> str:
    logger.info("Starting batch processing of file: %r", file_path)
    with open(file_path, mode="r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)

        if not reader.fieldnames or "question" not in reader.fieldnames:
            logger.error("Invalid CSV format: missing 'question' column in %r", file_path)
            raise ValueError("CSV file must contain a 'question' column.")

        rows = list(reader)  # Convert reader to list to preserve order
        questions = [row["question"] for row in rows]
        total_questions = len(questions)
        logger.info("Found %d questions to process", total_questions)

        # Process questions sequentially to avoid thread-safety issues with LiteLLM
        # Previous parallel implementation caused high CPU usage due to potential thread-safety
        # concerns in the underlying LLM client libraries
        processed_data = []

        progress_msg = cl.Message(content="Received file, starting batch processing...")
        await progress_msg.send()

        for i, q in enumerate(questions, 1):
            # Update progress message
            progress_msg.content = f"Processing question {i} of {total_questions}..."
            await progress_msg.update()
            logger.info("Processing question %d/%d", i, total_questions)

            processed_data.append(_process_question(q, engine))

        # Clean up progress message
        await progress_msg.remove()

        # Update rows with processed data while preserving original order
        for row, data in zip(rows, processed_data, strict=True):
            row.update(data)

        # Update fieldnames to include new columns
        all_fieldnames_dict = {
            f: None
            for f in list(reader.fieldnames) + [key for p in processed_data for key in p.keys()]
        }
        all_fieldnames = list(all_fieldnames_dict.keys())

    result_file = tempfile.NamedTemporaryFile(delete=False, mode="w", newline="", encoding="utf-8")
    writer = csv.DictWriter(result_file, fieldnames=all_fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    result_file.close()

    logger.info("Batch processing complete. Results written to: %r", result_file.name)
    return result_file.name

def _process_question(question: str, engine: ChatEngineInterface) -> dict[str, str | None]:
    logger.debug("Processing question: %r", question)
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

