import csv
import tempfile
from concurrent.futures import ThreadPoolExecutor

from src.chat_engine import ChatEngineInterface

async def batch_process(file_path: str, engine: ChatEngineInterface) -> str:
    with open(file_path, mode='r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        if 'question' not in reader.fieldnames:
            raise ValueError("CSV file must contain a 'question' column.")

        rows = list(reader)  # Convert reader to list to preserve order
        questions = [row['question'] for row in rows]

        # Process questions in parallel while preserving order
        with ThreadPoolExecutor() as executor:
            processed_data = list(executor.map(lambda q: process_question(q, engine), questions))

        # Update rows with processed data while preserving original order
        for row, data in zip(rows, processed_data):
            row.update(data)

        # Update fieldnames to include new columns
        all_fieldnames = reader.fieldnames + list(processed_data[0].keys())

    result_file = tempfile.NamedTemporaryFile(delete=False, mode='w', newline='', encoding='utf-8')
    writer = csv.DictWriter(result_file, fieldnames=all_fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    result_file.close()

    return result_file.name


def process_question(question: str, engine: ChatEngineInterface) -> dict[str, str]:
    result = engine.on_message(question=question, chat_history=[])
    return {"answer": result.response}
