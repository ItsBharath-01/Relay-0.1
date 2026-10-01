"""
mcp_test_server.py — Minimal test MCP server for Relay comprehensive tests.
"""
import os
import sys
import json
from mcp.server.mcpserver import MCPServer

server = MCPServer("relay-notes-server")

DB_FILE = os.path.join(os.path.dirname(__file__), ".test_notes_db.json")


def _load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_db(db):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2)
    except Exception:
        pass


@server.tool(name="create_note", description="Create a new note with title and content")
def create_note(title: str, content: str) -> dict:
    db = _load_db()
    note_id = f"note_{len(db) + 1}"
    record = {"id": note_id, "title": title, "content": content, "status": "created"}
    db[note_id] = record
    _save_db(db)
    return record


@server.tool(name="search_notes", description="Search notes by keyword query")
def search_notes(query: str) -> dict:
    db = _load_db()
    results = [
        n for n in db.values()
        if query.lower() in n.get("title", "").lower() or query.lower() in n.get("content", "").lower()
    ]
    return {
        "query": query,
        "results": results,
        "count": len(results),
        "found": len(results) > 0,
    }


@server.tool(name="update_note", description="Update an existing note's content")
def update_note(note_id: str, content: str) -> dict:
    db = _load_db()
    if note_id in db:
        db[note_id]["content"] = content
        _save_db(db)
        return {"id": note_id, "content": content, "status": "updated"}
    return {"error": "Note not found", "id": note_id}


@server.tool(name="delete_note", description="Delete a note by ID")
def delete_note(note_id: str) -> dict:
    db = _load_db()
    if note_id in db:
        del db[note_id]
        _save_db(db)
        return {"status": "deleted", "id": note_id}
    return {"status": "not_found", "id": note_id}


@server.tool(name="dangerous_wipe", description="Permanently delete all stored notes")
def dangerous_wipe() -> dict:
    _save_db({})
    return {"status": "wiped"}


if __name__ == "__main__":
    server.run(transport="stdio")
