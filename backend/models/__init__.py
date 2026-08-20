"""
Models package — Module 3 only owns fault_events.
M1 and M2 will register their own models (fault_readings, nodes, edges)
when they push their branches. No imports of their models here.
"""

from .fault_events import FaultEvent  # noqa: F401

__all__ = ["FaultEvent"]
