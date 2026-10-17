"""
MEMORA AI — Worker Identity & Lease Lifecycle Management
Provides unique worker process identification and renewable task execution heartbeats.
"""
import os
import socket
import logging
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

class WorkerIdentity:
    """
    Unique worker instance identifier.
    Distinct across machines, process IDs, and startup cycles.
    """
    _instance_id: Optional[str] = None

    @classmethod
    def get_worker_id(cls) -> str:
        if cls._instance_id is None:
            hostname = socket.gethostname().split(".")[0]
            pid = os.getpid()
            entropy = uuid4().hex[:8]
            cls._instance_id = f"memora-worker-{hostname}-{pid}-{entropy}"
            logger.info(f"Initialized local worker identity: {cls._instance_id}")
        return cls._instance_id

    @classmethod
    def set_worker_id(cls, custom_id: str) -> None:
        """Explicitly override worker identity (useful for multi-worker testing)."""
        cls._instance_id = custom_id

    @classmethod
    def reset(cls) -> None:
        """Reset to generate a fresh worker ID on next call."""
        cls._instance_id = None
