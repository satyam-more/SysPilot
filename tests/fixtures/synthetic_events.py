"""
Synthetic test events for use in integration tests.

Seed these into the test database before running agent loop tests.
"""

from backend.memory.models import EventCreate

SYNTHETIC_EVENTS: list[EventCreate] = [
    EventCreate(
        source="filesystem",
        event_type="file_modified",
        file_path="/home/user/projects/rust-notes/Rust_Notes.docx",
        title="Rust_Notes.docx",
        content_excerpt="Ownership Rules section updated — covered single owner per value",
        evidence_type="observed",
    ),
    EventCreate(
        source="shell",
        event_type="command_run",
        content_excerpt="cargo run",
        metadata={"exit_code": 1, "cwd": "/home/user/rust-project"},
        evidence_type="observed",
    ),
    EventCreate(
        source="shell",
        event_type="command_run",
        content_excerpt="cargo run",
        metadata={"exit_code": 0, "cwd": "/home/user/rust-project"},
        evidence_type="observed",
    ),
    EventCreate(
        source="filesystem",
        event_type="file_modified",
        file_path="/home/user/projects/rust-notes/Rust_Notes.docx",
        title="Rust_Notes.docx",
        content_excerpt="Borrowing rules noted — immutable vs mutable references",
        evidence_type="observed",
    ),
    EventCreate(
        source="shell",
        event_type="command_run",
        content_excerpt="cargo test",
        metadata={"exit_code": 0, "cwd": "/home/user/rust-project"},
        evidence_type="observed",
    ),
    EventCreate(
        source="filesystem",
        event_type="file_modified",
        file_path="/home/user/projects/python-notes/Python_Notes.md",
        title="Python_Notes.md",
        content_excerpt="List comprehensions and generator expressions",
        evidence_type="observed",
    ),
]

# Expected answer constraints for the canonical Rust question.
EXPECTED_ANSWERS = {
    "Where did I stop learning Rust?": {
        "must_reference_sources": ["Rust_Notes.docx", "cargo run", "cargo test"],
        "must_label_inferred": ["last section reached", "stopped at", "got to"],
        "must_not_claim": ["mastered ownership", "finished the book", "completed Rust"],
    }
}
