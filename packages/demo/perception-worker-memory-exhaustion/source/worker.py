"""
Perception Worker Runtime Entrypoint.
Responsible for continuous camera frame intake, batched tensor pre-processing,
inference execution, and publishing obstacle bounding boxes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("perception-worker")


class PerceptionWorker:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        resources = self.config.get("resources", {})
        self.memory_limit_mb = int(resources.get("memory_limit_mb", 512))
        runtime = self.config.get("runtime", {})
        self.max_batch_size = int(runtime.get("max_batch_size", 8))
        self.workers = int(runtime.get("workers", 2))
        self.request_timeout_ms = float(runtime.get("request_timeout_ms", 800))
        self.is_running = False

    def load_model(self) -> bool:
        logger.info(f"Loading perception model weights within {self.memory_limit_mb} MiB quota")
        return True

    def process_batch(self, frames: List[Any]) -> Dict[str, Any]:
        count = len(frames)
        if count > self.max_batch_size:
            frames = frames[:self.max_batch_size]
            count = len(frames)
        logger.debug(f"Processing perception batch of {count} frames")
        return {
            "batch_size": count,
            "detections": [],
            "status": "success",
        }

    def start(self) -> None:
        self.is_running = True
        logger.info(f"Perception worker started with {self.workers} workers")

    def stop(self) -> None:
        self.is_running = False
        logger.info("Perception worker stopped")


def create_worker(config: Optional[Dict[str, Any]] = None) -> PerceptionWorker:
    return PerceptionWorker(config)
