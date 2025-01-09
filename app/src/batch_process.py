import csv
import tempfile
import logging
import os
import signal
from concurrent.futures import ProcessPoolExecutor, TimeoutError
from typing import Any, List
from math import ceil

from src.chat_engine import ChatEngineInterface, create_engine
from src.citations import simplify_citation_numbers

logger = logging.getLogger(__name__)

# Get optimal number of workers based on CPU cores
OPTIMAL_WORKERS = min(os.cpu_count() or 4, 4)  # Cap at 4 workers
BATCH_SIZE = 3  # Process questions in batches of 3
QUESTION_TIMEOUT = 10  # 10 seconds per question timeout


def _process_question_worker(question: str) -> dict[str, str | None]:
    """Worker function that creates its own engine instance"""
    # Set up process signal handler
    def handle_timeout(signum, frame):
        raise TimeoutError("Question processing timed out")
    
    signal.signal(signal.SIGALRM, handle_timeout)
    signal.alarm(QUESTION_TIMEOUT)  # Set timeout
    
    logger.info(f"Starting to process question: {question[:50]}...")
    try:
        # Create a new engine instance in the worker process
        logger.info("Creating new engine instance...")
        engine = create_engine("ca-edd-web")
        logger.info("Engine created successfully")

        # Make the LLM call with detailed logging
        logger.info("Sending question to LLM...")
        result = engine.on_message(question=question, chat_history=[])
        logger.info("Received response from LLM")

        # Process the response
        logger.info("Processing citations...")
        final_result = simplify_citation_numbers(result)

        result_table: dict[str, str | None] = {"answer": final_result.response}

        # Process subsections with logging
        logger.info(f"Processing {len(final_result.subsections)} subsections...")
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
        
        logger.info(f"Finished processing question: {question[:50]}...")
        return result_table
    except TimeoutError as e:
        logger.error("Question processing timed out")
        return {"answer": "Error: Processing timed out"}
    except Exception as e:
        logger.error(f"Error processing question: {str(e)}", exc_info=True)
        return {"answer": f"Error processing question: {str(e)}"}
    finally:
        signal.alarm(0)  # Disable the alarm


def _process_batch(questions: List[str], executor) -> List[dict[str, str | None]]:
    """Process a batch of questions using the executor"""
    futures = [executor.submit(_process_question_worker, q) for q in questions]
    results = []
    for i, future in enumerate(futures):
        try:
            result = future.result(timeout=QUESTION_TIMEOUT + 2)  # Slightly longer than worker timeout
            results.append(result)
        except Exception as e:
            logger.error(f"Error in batch question {i}: {str(e)}")
            results.append({"answer": f"Error: {str(e)}"})
    return results


async def batch_process(file_path: str, engine: ChatEngineInterface) -> str:
    logger.info("Starting batch processing...")
    with open(file_path, mode="r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        logger.info("CSV file opened successfully")

        if not reader.fieldnames or "question" not in reader.fieldnames:
            raise ValueError("CSV file must contain a 'question' column.")

        rows = list(reader)  # Convert reader to list to preserve order
        questions = [row["question"] for row in rows]
        total_questions = len(questions)
        logger.info(f"Loaded {total_questions} questions from CSV")

        # Process questions in batches
        processed_data = []
        logger.info(f"Starting parallel processing with {OPTIMAL_WORKERS} workers...")
        with ProcessPoolExecutor(max_workers=OPTIMAL_WORKERS) as executor:
            logger.info("Created ProcessPoolExecutor")
            
            try:
                # Process questions in batches
                for batch_start in range(0, total_questions, BATCH_SIZE):
                    batch_end = min(batch_start + BATCH_SIZE, total_questions)
                    batch = questions[batch_start:batch_end]
                    logger.info(f"Processing batch {batch_start//BATCH_SIZE + 1}/{ceil(total_questions/BATCH_SIZE)}")
                    
                    batch_results = _process_batch(batch, executor)
                    processed_data.extend(batch_results)
                    
                    logger.info(f"Completed {batch_end}/{total_questions} questions")
            except Exception as e:
                logger.error(f"Batch processing error: {str(e)}", exc_info=True)
                # Add error results for remaining questions
                remaining = total_questions - len(processed_data)
                processed_data.extend([{"answer": "Error: Batch processing failed"}] * remaining)

        logger.info("Completed all question processing")

        # Update rows with processed data while preserving original order
        logger.info("Updating rows with processed data...")
        for row, data in zip(rows, processed_data, strict=True):
            row.update(data)

        # Update fieldnames to include new columns
        all_fieldnames_dict = {
            f: None
            for f in list(reader.fieldnames) + [key for p in processed_data for key in p.keys()]
        }
        all_fieldnames = list(all_fieldnames_dict.keys())

    logger.info("Writing results to temporary file...")
    result_file = tempfile.NamedTemporaryFile(delete=False, mode="w", newline="", encoding="utf-8")
    writer = csv.DictWriter(result_file, fieldnames=all_fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    result_file.close()
    logger.info("Batch processing completed successfully")

    return result_file.name
