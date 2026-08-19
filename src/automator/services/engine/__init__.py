"""Processing engine: watches the folder and processes PDFs in the background.

It is agnostic to the graphical interface: it communicates events through a
callback (EventSink), so the UI (or the tests) decides how to react.
"""

from automator.services.engine.events import ConfigProvider, EngineEvent, EngineEventType, EventSink
from automator.services.engine.lifecycle import ProcessingEngine

__all__ = [
    "ConfigProvider",
    "EngineEvent",
    "EngineEventType",
    "EventSink",
    "ProcessingEngine",
]
