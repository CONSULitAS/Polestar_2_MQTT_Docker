"""Application orchestration boundary.

Startup, dependency wiring, polling, error recovery, and graceful shutdown
belong in this module. The executable switch from the legacy script takes place
after the dependent configuration, API, and publisher tasks are implemented.
"""

