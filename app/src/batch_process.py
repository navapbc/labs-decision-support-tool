import csv
import tempfile
from concurrent.futures import ThreadPoolExecutor

from src.chat_engine import ChatEngineInterface
from src.citations import remap_citation_ids
from src.format import replace_citation_ids


async def batch_process(file_path: str, engine: ChatEngineInterface) -> str:
    with open(file_path, mode="r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)

        if not reader.fieldnames or "question" not in reader.fieldnames:
            raise ValueError("CSV file must contain a 'question' column.")

        rows = list(reader)  # Convert reader to list to preserve order
        questions = [row["question"] for row in rows]

        # Process questions in parallel while preserving order
        with ThreadPoolExecutor() as executor:
            processed_data = list(executor.map(lambda q: _process_question(q, engine), questions))

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

    return result_file.name


def _process_question(question: str, engine: ChatEngineInterface) -> dict[str, str | None]:
    result = engine.on_message(question=question, chat_history=[])

    remapped_citations = remap_citation_ids(result.subsections, result.response)
    response_with_remapped_citations = replace_citation_ids(result.response, remapped_citations)

    result_table: dict[str, str | None] = {"answer": response_with_remapped_citations}

    for subsection in remapped_citations.values():
        citation_key = "citation_" + subsection.id
        result_table |= {
            citation_key: subsection.text,
            citation_key + "_name": subsection.chunk.document.name,
            citation_key + "_source": subsection.chunk.document.source,
        }

    return result_table
