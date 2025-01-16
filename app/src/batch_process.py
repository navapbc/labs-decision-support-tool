import time
import logging
import csv
import tempfile
from concurrent.futures import ThreadPoolExecutor

from src.chat_engine import ChatEngineInterface
from src.citations import simplify_citation_numbers

logger = logging.getLogger(__name__)

import concurrent.futures
async def batch_process(file_path: str, engine: ChatEngineInterface) -> str:
    with open(file_path, mode="r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)

        if not reader.fieldnames or "question" not in reader.fieldnames:
            raise ValueError("CSV file must contain a 'question' column.")

        rows = list(reader)  # Convert reader to list to preserve order
        questions = [row["question"] for row in rows]

        if not True:
            # await asyncio.sleep(65)  # Works
            time.sleep(65)  # Doesn't work
            logger.info("Writing results to OLD file /tmp/tmpjan8_yq2")
            return "/tmp/tmpjan8_yq2"

        # Process questions in parallel while preserving order
        processed_data = []
        with ThreadPoolExecutor() as executor:
            # processed_data = list(executor.map(lambda args: _process_question(args[0], args[1], engine), enumerate(questions)))

            future_to_url = {executor.submit(_process_question, i, q, engine): q for i, q in enumerate(questions)}

            loop = asyncio.get_running_loop()
            # blocking_call(processed_data, future_to_url)
            await loop.run_in_executor(executor, blocking_call, processed_data, future_to_url)
        logger.info("Got %i results", len(processed_data))

        # Update rows with processed data while preserving original order
        for row, data in zip(rows, processed_data, strict=True):
            row.update(data)    # ROOT CAUSE?: Blocking call
        logger.info("Updated results: %r", rows[0].keys())

        # Update fieldnames to include new columns
        all_fieldnames_dict = {
            f: None
            for f in list(reader.fieldnames) + [key for p in processed_data for key in p.keys()]
        }
        all_fieldnames = list(all_fieldnames_dict.keys())

    result_file = tempfile.NamedTemporaryFile(delete=False, mode="w", newline="", encoding="utf-8")
    logger.info("Writing results to file %r", result_file.name)
    writer = csv.DictWriter(result_file, fieldnames=all_fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    result_file.close()

    return result_file.name

def blocking_call(processed_data, future_to_url):
    for future in concurrent.futures.as_completed(future_to_url): # This blocks as well!
        url = future_to_url[future]
        try:
            data = future.result()
            processed_data.append(data)
        except Exception as exc:
            print('%r generated an exception: %s' % (url, exc))
        else:
            print('%r page is %d bytes' % (url, len(data)))

import asyncio
def _process_question(index: int, question: str, engine: ChatEngineInterface) -> dict[str, str | None]:
    # FIXME: catch and handle exceptions
    logger.info("Processing question %i: %s...", index, question[:50])
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
        # time.sleep(65)
        asyncio.run(asyncio.sleep(65))
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

    logger.info("Processed question %i", index)
    return result_table
