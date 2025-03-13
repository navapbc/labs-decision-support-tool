#!/usr/bin/env python3

import json
import time
from typing import Any, Dict

import requests

from src.chat_engine import ImagineLaEngine, CaEddWebEngine
from src.profiling_stats import get_profiling_stats

TEST_QUERIES = [
    "What documents do I need to apply for Covered California?",
    "How can I find an Access Center in Los Angeles?",
    "What are the income requirements for the California Child and Dependent Care Tax Credit?"
]

def run_query(query: str) -> Dict[str, Any]:
    """Run a query and return timing information"""
    start_time = time.perf_counter()
    
    # Track analyze_message timing
    analyze_start = time.perf_counter()
    response = requests.post(
        "http://main-app:8000/api/query",
        json={
            "user_id": "test_user",  # Add required user_id field
            "session_id": str(time.time()),  # Use timestamp as session ID
            "new_session": True,
            "message": query
        }
    )
    analyze_end = time.perf_counter()
    
    end_time = time.perf_counter()
    
    try:
        print(f"\nResponse content: {response.content}")  # Debug line
        result = response.json()
        profiling = result.get("profiling", {})
        
        timings = {
            "total_duration": end_time - start_time,
            "http_request_time": analyze_end - analyze_start,
            "component_timings": profiling.get("component_timings", {}),
            "metadata": profiling.get("metadata", {}),
            "system_metrics": profiling.get("system_metrics", {})
        }
        
        # Add response details
        timings["response"] = {
            "status": response.status_code,
            "length": len(result.get("response_text", "")),
            "has_context": bool(result.get("citations", [])),
            "num_chunks": len(result.get("citations", [])),
            "attributes": result.get("attributes", {})
        }
        
        return timings
        
    except Exception as e:
        return {
            "error": str(e),
            "total_duration": end_time - start_time,
            "http_request_time": analyze_end - analyze_start
        }

def print_timing_summary(query: str, timings: Dict[str, Any]) -> None:
    """Print a summary of timing information"""
    print(f"\nQuery: {query}")
    print("-" * 80)
    
    if "error" in timings:
        print(f"Error: {timings['error']}")
        print(f"Total time: {timings['total_duration']:.3f}s")
        return
        
    print(f"Total time: {timings['total_duration']:.3f}s")
    print(f"HTTP request time: {timings['http_request_time']:.3f}s")
    
    if timings["component_timings"]:
        print("\nComponent Timings:")
        for component, duration in timings["component_timings"].items():
            print(f"  {component}: {duration:.3f}s")
            
    if timings["metadata"]:
        print("\nMetadata:")
        for key, value in timings["metadata"].items():
            print(f"  {key}: {value}")
            
    if timings["system_metrics"]:
        print("\nSystem Metrics:")
        for key, value in timings["system_metrics"].items():
            if isinstance(value, dict):
                print(f"  {key}:")
                for k, v in value.items():
                    print(f"    {k}: {v}")
            else:
                print(f"  {key}: {value}")
                
    print("\nResponse Details:")
    resp = timings["response"]
    print(f"  Status: {resp['status']}")
    print(f"  Response length: {resp['length']} chars")
    print(f"  Has context: {resp['has_context']}")
    print(f"  Number of chunks: {resp['num_chunks']}")
    if resp["attributes"]:
        print("  Message attributes:")
        for key, value in resp["attributes"].items():
            print(f"    {key}: {value}")

def main():
    print("\nRunning profiling tests...")
    
    all_timings = []
    for query in TEST_QUERIES:
        print(f"\nTesting: {query}")
        timings = run_query(query)
        all_timings.append(timings)
        print_timing_summary(query, timings)
        
    # Print overall summary
    print("\nOverall Summary:")
    print("-" * 80)
    total_times = [t["total_duration"] for t in all_timings if "error" not in t]
    if total_times:
        print(f"Average query time: {sum(total_times) / len(total_times):.3f}s")
        print(f"Min query time: {min(total_times):.3f}s")
        print(f"Max query time: {max(total_times):.3f}s")
        
    # Component timing averages
    components = {}
    for timing in all_timings:
        if "error" not in timing:
            for component, duration in timing["component_timings"].items():
                if component not in components:
                    components[component] = []
                components[component].append(duration)
                
    if components:
        print("\nAverage Component Times:")
        for component, times in components.items():
            avg_time = sum(times) / len(times)
            print(f"  {component}: {avg_time:.3f}s")

if __name__ == "__main__":
    main() 