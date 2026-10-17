"""
Tool registry for the agent harness.

Each tool has:
  - name: identifier the model uses to call it
  - description: shown to the model in the system prompt
  - input_schema: Pydantic model for validation
  - execute(): runs the tool and returns a JSON-serialisable dict

Tools never generate SQL directly — they call the memory layer functions.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from backend.memory.search import get_event, list_events, search_events

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

class SearchEventsInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    source: Optional[str] = None


class GetEventInput(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)


class ListEventsInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    source: Optional[str] = None


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

class SearchEventsTool:
    name = "search_events"
    description = (
        "Search the activity event database using full-text search. "
        "Returns events matching the query, ordered by relevance. "
        "Use this to find what the user was working on."
    )
    input_schema = SearchEventsInput

    def execute(self, raw_input: dict[str, Any]) -> dict:
        inp = self.input_schema.model_validate(raw_input)
        events = search_events(
            query=inp.query,
            limit=inp.limit,
            start_time=inp.start_time,
            end_time=inp.end_time,
            source=inp.source,
        )
        return {
            "events": [e.model_dump(mode="json") for e in events],
            "count": len(events),
        }


class GetEventTool:
    name = "get_event"
    description = (
        "Fetch the full details of a single event by its id. "
        "Use this after search_events to get the complete record for a specific result."
    )
    input_schema = GetEventInput

    def execute(self, raw_input: dict[str, Any]) -> dict:
        inp = self.input_schema.model_validate(raw_input)
        event = get_event(inp.event_id)
        if event is None:
            return {"error": "Event not found", "event_id": inp.event_id}
        return {"event": event.model_dump(mode="json")}


class ListEventsTool:
    name = "list_events"
    description = (
        "List recent permitted events in reverse chronological order. "
        "Use this for a broad overview when you don't have a specific query."
    )
    input_schema = ListEventsInput

    def execute(self, raw_input: dict[str, Any]) -> dict:
        inp = self.input_schema.model_validate(raw_input)
        events = list_events(limit=inp.limit, offset=inp.offset, source=inp.source)
        return {
            "events": [e.model_dump(mode="json") for e in events],
            "count": len(events),
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_TOOLS: dict[str, Any] = {
    t.name: t
    for t in [SearchEventsTool(), GetEventTool(), ListEventsTool()]
}


def get_tool(name: str) -> Any | None:
    """Return a tool instance by name, or None if not registered."""
    return _TOOLS.get(name)


def all_tools() -> list[Any]:
    """Return all registered tool instances."""
    return list(_TOOLS.values())


def tool_schemas_for_model() -> list[dict]:
    """
    Return tool definitions in the format expected by OpenAI-compatible APIs.
    Also used to build the system prompt for Ollama.
    """
    schemas = []
    for tool in _TOOLS.values():
        schema = tool.input_schema.model_json_schema()
        schemas.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": schema,
            },
        })
    return schemas
