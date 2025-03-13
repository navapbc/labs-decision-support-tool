import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

@dataclass
class QueryStats:
    query_type: str
    start_time: datetime
    duration: float
    component_timings: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    system_metrics: Dict[str, float] = field(default_factory=dict)

class ProfilingStats:
    def __init__(self, db_url: Optional[str] = None):
        self.stats: List[QueryStats] = []
        self.current_window: List[QueryStats] = []
        self.window_size = 100  # Number of queries to keep in memory
        self.db_url = db_url
        self.db_engine = create_engine(db_url) if db_url else None
        
    def add_query(self, stats: QueryStats):
        """Add a new query's stats to the collection"""
        self.stats.append(stats)
        self.current_window.append(stats)
        
        if len(self.current_window) > self.window_size:
            self._persist_window()
            self.current_window = []
            
    def _persist_window(self):
        """Save the current window of stats to storage"""
        if not self.current_window:
            return
            
        if self.db_engine:
            with Session(self.db_engine) as session:
                for stat in self.current_window:
                    session.execute(
                        """
                        INSERT INTO query_stats 
                        (query_type, start_time, duration, component_timings, metadata, system_metrics)
                        VALUES (:query_type, :start_time, :duration, :component_timings, :metadata, :system_metrics)
                        """,
                        {
                            "query_type": stat.query_type,
                            "start_time": stat.start_time,
                            "duration": stat.duration,
                            "component_timings": json.dumps(stat.component_timings),
                            "metadata": json.dumps(stat.metadata),
                            "system_metrics": json.dumps(stat.system_metrics)
                        }
                    )
                session.commit()
        else:
            # If no DB configured, write to log file
            for stat in self.current_window:
                logger.info("Query Stats: %s", json.dumps({
                    "query_type": stat.query_type,
                    "start_time": stat.start_time.isoformat(),
                    "duration": stat.duration,
                    "component_timings": stat.component_timings,
                    "metadata": stat.metadata,
                    "system_metrics": stat.system_metrics
                }))
                
    def get_stats(self, query_type: Optional[str] = None, 
                 start_time: Optional[datetime] = None,
                 end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get aggregated stats for the specified filters"""
        filtered_stats = self.stats
        
        if query_type:
            filtered_stats = [s for s in filtered_stats if s.query_type == query_type]
            
        if start_time:
            filtered_stats = [s for s in filtered_stats if s.start_time >= start_time]
            
        if end_time:
            filtered_stats = [s for s in filtered_stats if s.start_time <= end_time]
            
        if not filtered_stats:
            return {}
            
        durations = [s.duration for s in filtered_stats]
        component_times = defaultdict(list)
        for stat in filtered_stats:
            for component, time in stat.component_timings.items():
                component_times[component].append(time)
                
        return {
            "count": len(filtered_stats),
            "duration": {
                "mean": np.mean(durations),
                "median": np.median(durations),
                "p95": np.percentile(durations, 95),
                "min": min(durations),
                "max": max(durations)
            },
            "components": {
                component: {
                    "mean": np.mean(times),
                    "median": np.median(times),
                    "p95": np.percentile(times, 95)
                }
                for component, times in component_times.items()
            }
        }
        
    def get_recent_trends(self, window_minutes: int = 60) -> Dict[str, Any]:
        """Get trend data for the last window_minutes"""
        now = datetime.now()
        cutoff = now.timestamp() - (window_minutes * 60)
        
        recent_stats = [s for s in self.stats if s.start_time.timestamp() >= cutoff]
        if not recent_stats:
            return {}
            
        # Group by minute
        by_minute = defaultdict(list)
        for stat in recent_stats:
            minute = int(stat.start_time.timestamp() / 60) * 60
            by_minute[minute].append(stat)
            
        return {
            "by_minute": {
                ts: {
                    "count": len(stats),
                    "avg_duration": np.mean([s.duration for s in stats]),
                    "p95_duration": np.percentile([s.duration for s in stats], 95)
                }
                for ts, stats in by_minute.items()
            }
        }

# Global stats instance
_stats = ProfilingStats()

def get_profiling_stats() -> ProfilingStats:
    """Get the global profiling stats instance"""
    return _stats 