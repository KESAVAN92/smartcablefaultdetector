"""
Module 3 — Fault-to-Graph Mapping & Live Digital Map
Package init: exports module3_bp and the init function called by app.py.

File ownership (conflict-prevention reference):
  backend/modules/module1.py          → Module 1 team (untouched by M3)
  backend/modules/module2.py          → Module 2 team (untouched by M3)
  backend/modules/module3/            → Module 3 (this entire folder)
  backend/modules/module4.py          → Module 4 team (untouched by M3)
  backend/models/fault_events.py      → Module 3 (the only table we own)
  backend/database.py                 → shared infrastructure
"""

from .routes import module3_bp, ReadingsNamespace, FaultEventsNamespace

__all__ = ["module3_bp", "init_module3"]


def init_module3(socketio, *, start_background=True):
    """
    Wire Module 3's services and start the M1 background emitter.
    Called from app.py after SocketIO + DB are initialised.
    """
    from .mapping_service import init_mapping_service, process_reading
    from .adapters.module1_adapter import init_module1_adapter

    # Register SocketIO namespaces
    socketio.on_namespace(ReadingsNamespace("/readings"))
    socketio.on_namespace(FaultEventsNamespace("/fault-events"))

    init_mapping_service(socketio)
    # Pass process_reading callback to avoid circular import in the adapter
    init_module1_adapter(
      socketio,
      mapping_process_fn=process_reading,
      start_background=start_background,
    )
