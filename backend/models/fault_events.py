"""
FaultEvent model — owned entirely by Module 3.

CONFLICT-FREE DESIGN:
- reading_id, nearest_node_id, edge_id are plain String columns (no ForeignKey).
  This means SQLAlchemy never needs fault_readings / nodes / edges tables to
  exist before creating this table — M1 and M2 can push independently.
- Relational integrity is enforced at the application layer (mapping_service).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, Float, Index, String

from database import Base


class FaultEvent(Base):
    __tablename__ = "fault_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Soft references — no FK constraints so table is independent of M1/M2
    reading_id = Column(String, nullable=False, index=True)       # → fault_readings.id
    nearest_node_id = Column(String, nullable=False, index=True)  # → nodes.id
    edge_id = Column(String, nullable=True)                       # → edges.id (None = exact node)
    distance_along_edge_m = Column(Float, nullable=True)          # offset within the edge

    status = Column(
        Enum("open", "acknowledged", "resolved", name="fault_event_status"),
        nullable=False,
        default="open",
    )
    acknowledged_by = Column(String, nullable=True)   # user-ID placeholder (auth = Module 4)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Composite index for the most common query (list events by node + status)
    __table_args__ = (
        Index("ix_fe_node_status", "nearest_node_id", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "reading_id": self.reading_id,
            "nearest_node_id": self.nearest_node_id,
            "edge_id": self.edge_id,
            "distance_along_edge_m": self.distance_along_edge_m,
            "status": self.status,
            "acknowledged_by": self.acknowledged_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
