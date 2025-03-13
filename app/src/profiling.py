import asyncio
import functools
import json
import logging
import os
import time
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import psutil
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from src.profiling_stats import QueryStats, get_profiling_stats

logger = logging.getLogger(__name__)

# Context variables to store profiling data
_request_start_time: ContextVar[float] = ContextVar("request_start_time")
_component_timings: ContextVar[Dict[str, float]] = ContextVar("component_timings", default={})
_metadata: ContextVar[Dict[str, Any]] = ContextVar("metadata", default={})

request_context: ContextVar[dict] = ContextVar("request_context", default={})

class ProfilingStats:
    """Container for profiling statistics"""
    def __init__(self):
        self.timings: List[Dict[str, float]] = []
        self.metadata: Dict[str, Any] = {}
    
    def add_timing(self, name: str, duration: float, metadata: Optional[Dict[str, Any]] = None):
        timing = {"name": name, "duration": duration}
        if metadata:
            timing.update(metadata)
        self.timings.append(timing)
    
    def get_total_duration(self) -> float:
        return sum(t["duration"] for t in self.timings)
    
    def get_component_breakdown(self) -> Dict[str, float]:
        """Get percentage breakdown of time spent in each component"""
        total = self.get_total_duration()
        if total == 0:
            return {}
        return {
            t["name"]: (t["duration"] / total) * 100 
            for t in self.timings
        }
    
    def to_json(self) -> str:
        return json.dumps({
            "timings": self.timings,
            "metadata": self.metadata,
            "total_duration": self.get_total_duration(),
            "component_breakdown": self.get_component_breakdown()
        }, indent=2)

def profile_function(component_name: str) -> Callable:
    """Decorator to profile a function's execution time"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.perf_counter() - start_time
                component_timings = _component_timings.get()
                component_timings[component_name] = duration
                _component_timings.set(component_timings)
        return wrapper
    return decorator

def get_request_stats() -> Optional[ProfilingStats]:
    """Get profiling stats for current request context"""
    ctx = request_context.get()
    return ctx.get("stats")

def reset_request_stats():
    """Reset profiling stats for current request context"""
    ctx = request_context.get()
    ctx["stats"] = ProfilingStats()

def add_metadata(key: str, value: Any) -> None:
    """Add metadata to the current request context"""
    metadata = _metadata.get()
    metadata[key] = value
    _metadata.set(metadata)

def get_system_metrics() -> Dict[str, float]:
    """Get current system resource usage"""
    process = psutil.Process(os.getpid())
    
    return {
        "cpu_percent": process.cpu_percent(),
        "memory_percent": process.memory_percent(),
        "memory_rss": process.memory_info().rss / 1024 / 1024,  # MB
        "open_files": len(process.open_files()),
        "threads": process.num_threads(),
        "connections": len(process.connections())
    }

class ProfilingMiddleware(BaseHTTPMiddleware):
    """Middleware to collect request profiling data"""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Initialize context for this request
        start_time = time.perf_counter()
        _request_start_time.set(start_time)
        _component_timings.set({})
        _metadata.set({})
        
        # Add basic request metadata
        add_metadata("path", request.url.path)
        add_metadata("method", request.method)
        add_metadata("client_host", request.client.host if request.client else None)
        
        try:
            # Get system metrics at start
            start_metrics = get_system_metrics()
            
            # Process request
            response = await call_next(request)
            
            # Calculate duration and get final metrics
            duration = time.perf_counter() - start_time
            end_metrics = get_system_metrics()
            
            # Store query stats
            query_type = request.url.path.split("/")[-1]  # Use last path segment as query type
            stats = QueryStats(
                query_type=query_type,
                start_time=datetime.fromtimestamp(start_time),
                duration=duration,
                component_timings=_component_timings.get(),
                metadata=_metadata.get(),
                system_metrics={
                    "start": start_metrics,
                    "end": end_metrics,
                    "delta": {
                        k: end_metrics[k] - start_metrics[k]
                        for k in start_metrics.keys()
                    }
                }
            )
            
            # Add to global stats
            get_profiling_stats().add_query(stats)
            
            # Log summary
            logger.info(
                "Request profiling: path=%s duration=%.3fs components=%s",
                request.url.path,
                duration,
                _component_timings.get()
            )
            
            return response
            
        except Exception as e:
            # Log error but don't interfere with error handling
            logger.exception("Error in profiling middleware")
            raise
            
        finally:
            # Clean up context
            _component_timings.set({})
            _metadata.set({}) 