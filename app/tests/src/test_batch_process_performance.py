import os
import time
import psutil
import pytest
import logging
import asyncio
from src.batch_process import batch_process, _process_question_worker
from src.chat_engine import create_engine
import tempfile

# Set HuggingFace tokenizer parallelism to avoid forking warnings
os.environ["TOKENIZERS_PARALLELISM"] = "false"

logger = logging.getLogger(__name__)


def get_thread_stats(process):
    """Get detailed stats about threads"""
    threads = process.threads()
    total_cpu = 0
    for thread in threads:
        try:
            total_cpu += process.cpu_percent(interval=0.1)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {
        'thread_count': len(threads),
        'total_cpu': total_cpu
    }


async def monitor_resources(process, stop_monitoring):
    """Monitor system resources and log them"""
    monitoring_data = []
    start_time = time.time()
    
    while not stop_monitoring.is_set():
        stats = get_thread_stats(process)
        memory = process.memory_info().rss / 1024 / 1024
        current_time = time.time() - start_time
        
        data = {
            'time': current_time,
            'threads': stats['thread_count'],
            'cpu': stats['total_cpu'],
            'memory': memory
        }
        monitoring_data.append(data)
        
        logger.warning(
            f"[MONITOR] Time: {current_time:.1f}s | "
            f"Threads: {stats['thread_count']} | "
            f"CPU: {stats['total_cpu']:.1f}% | "
            f"Memory: {memory:.1f}MB"
        )
        
        await asyncio.sleep(1)
    
    return monitoring_data


@pytest.mark.performance
def test_single_question_processing():
    """Test processing a single question to measure baseline resource usage"""
    test_question = "What is the maximum SNAP benefit amount?"
    
    process = psutil.Process()
    initial_cpu = process.cpu_percent()
    initial_memory = process.memory_info().rss / 1024 / 1024
    start_time = time.time()
    
    result = _process_question_worker(test_question)
    
    processing_time = time.time() - start_time
    final_memory = process.memory_info().rss / 1024 / 1024
    final_cpu = process.cpu_percent()
    
    logger.warning(f"Single Question Processing Metrics:")
    logger.warning(f"Processing Time: {processing_time:.2f}s")
    logger.warning(f"CPU Usage: {final_cpu:.1f}%")
    logger.warning(f"Memory Growth: {final_memory - initial_memory:.1f}MB")
    
    # Verify the result structure
    assert "answer" in result, "Result should contain an answer"
    assert isinstance(result["answer"], str), "Answer should be a string"
    
    # Performance assertions
    assert processing_time < 10, "Single question processing took too long"
    assert final_cpu < 200, "Single question processing used too much CPU"
    assert (final_memory - initial_memory) < 512, "Single question used too much memory"


@pytest.mark.performance
@pytest.mark.asyncio
async def test_process_pool_behavior():
    """Test ProcessPoolExecutor behavior with a small set of controlled questions"""
    # Create a small CSV with known questions
    csv_content = (
        "question\n"
        "What is SNAP?\n"
        "How do I apply for benefits?\n"
        "What documents do I need?\n"
        "When will I receive benefits?\n"
    )
    
    # Create temporary CSV file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        f.write(csv_content)
        temp_csv = f.name
    
    engine = create_engine("ca-edd-web")
    process = psutil.Process()
    initial_memory = process.memory_info().rss / 1024 / 1024
    question_times = []
    
    try:
        logger.warning("Starting process pool test with controlled questions")
        overall_start = time.time()
        
        # Setup monitoring
        stop_monitoring = asyncio.Event()
        monitor_task = asyncio.create_task(monitor_resources(process, stop_monitoring))
        
        # Process the CSV
        async with asyncio.timeout(30):
            result = await batch_process(temp_csv, engine)
        overall_time = time.time() - overall_start
        
        # Stop monitoring
        stop_monitoring.set()
        monitoring_data = await monitor_task
        
        # Read and verify the results
        with open(result, 'r') as f:
            result_content = f.read()
            
        # Log performance metrics
        logger.warning("\nProcess Pool Performance Summary:")
        logger.warning(f"Total Processing Time: {overall_time:.2f}s")
        logger.warning(f"Average Time per Question: {overall_time/4:.2f}s")
        if monitoring_data:
            logger.warning(f"Peak CPU: {max(d['cpu'] for d in monitoring_data):.1f}%")
            logger.warning(f"Peak Memory: {max(d['memory'] for d in monitoring_data):.1f}MB")
            logger.warning(f"Peak Threads: {max(d['threads'] for d in monitoring_data)}")
        
        # Verify results
        assert result_content.count('\n') >= 5, "Should have header + 4 result rows"
        assert 'answer' in result_content, "Should have answer column in results"
        
        # Performance assertions
        assert overall_time < 40, "Small batch should complete in under 40 seconds"
        if monitoring_data:
            assert max(d['cpu'] for d in monitoring_data) < 1000, "CPU usage too high"
            assert max(d['threads'] for d in monitoring_data) < 100, "Too many threads"
            assert (max(d['memory'] for d in monitoring_data) - initial_memory) < 1024, "Memory growth too high"
        
    finally:
        # Cleanup temporary files
        os.unlink(temp_csv)
        try:
            os.unlink(result)
        except:
            pass


@pytest.mark.performance
@pytest.mark.asyncio
async def test_batch_process_performance_with_sample_csv():
    """Full integration performance test with actual CSV file"""
    csv_path = os.path.join("tests", "src", "test_data", "clean_test_questions_1.csv")
    engine = create_engine("ca-edd-web")
    
    process = psutil.Process()
    initial_stats = get_thread_stats(process)
    initial_memory = process.memory_info().rss / 1024 / 1024
    
    logger.warning(f"Starting performance test with initial state:")
    logger.warning(f"Initial threads: {initial_stats['thread_count']}")
    logger.warning(f"Initial memory: {initial_memory:.1f}MB")
    
    # Setup monitoring with timeout
    stop_monitoring = asyncio.Event()
    monitor_task = asyncio.create_task(monitor_resources(process, stop_monitoring))
    
    try:
        # Run batch processing with timeout
        start_time = time.time()
        async with asyncio.timeout(60):
            result = await batch_process(csv_path, engine)
        processing_time = time.time() - start_time
            
        # Stop monitoring and ensure we get the data
        stop_monitoring.set()
        monitoring_data = await monitor_task
        
        if not monitoring_data:
            logger.error("No monitoring data collected!")
            monitoring_data = [{
                'time': processing_time,
                'threads': process.num_threads(),
                'cpu': process.cpu_percent(),
                'memory': process.memory_info().rss / 1024 / 1024
            }]
        
        # Read results to verify success
        with open(result, 'r') as f:
            result_content = f.read()
            result_lines = result_content.count('\n')
        
        # Log summary
        logger.warning("\nPerformance Summary:")
        logger.warning(f"Total Processing Time: {processing_time:.2f}s")
        logger.warning(f"Data points collected: {len(monitoring_data)}")
        logger.warning(f"Peak threads: {max(d['threads'] for d in monitoring_data)}")
        logger.warning(f"Peak CPU: {max(d['cpu'] for d in monitoring_data):.1f}%")
        logger.warning(f"Peak Memory: {max(d['memory'] for d in monitoring_data):.1f}MB")
        logger.warning(f"Result rows: {result_lines}")
        
        # Assertions
        assert processing_time < 60, "Processing took too long"
        assert max(d['cpu'] for d in monitoring_data) < 1000, "CPU usage exceeded 1000%"
        assert max(d['threads'] for d in monitoring_data) < 100, "Too many threads created"
        assert (max(d['memory'] for d in monitoring_data) - initial_memory) < 1024, "Memory growth exceeded 1GB"
        assert result_lines > 1, "No results were generated"
        
    except asyncio.TimeoutError:
        logger.error("Test timed out after 5 minutes")
        raise
    except Exception as e:
        logger.error(f"Error during batch processing: {str(e)}")
        final_stats = get_thread_stats(process)
        logger.error(f"Final state - Threads: {final_stats['thread_count']}, "
                    f"CPU: {final_stats['total_cpu']:.1f}%, "
                    f"Memory: {process.memory_info().rss / 1024 / 1024:.1f}MB")
        raise
    finally:
        # Ensure monitoring is stopped
        if not stop_monitoring.is_set():
            stop_monitoring.set()
            try:
                await monitor_task
            except Exception:
                pass 