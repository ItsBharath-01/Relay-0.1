"""
mcp_test_server.py — Relay test MCP server.

Default transport selection:
  • If stdin is NOT a TTY (subprocess piped I/O) → stdio transport (for test harness use)
  • If --transport is supplied on the CLI → honour it
  • If stdin IS a TTY and no --transport → streamable-http on 127.0.0.1:8085/mcp

Relay UI registers MCP servers at:  http://127.0.0.1:8085/mcp

Direct startup commands:
    python tests/mcp_test_server.py                              # auto-detects; HTTP if TTY
    python tests/mcp_test_server.py --transport streamable-http  # explicit HTTP
    python tests/mcp_test_server.py --transport stdio            # explicit stdio

Tools exposed:
    create_note, search_notes, update_note, delete_note, dangerous_wipe, health
"""
import datetime
import json
import os
import sys

from mcp.server.mcpserver import MCPServer

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------
server = MCPServer("relay-notes-server")

# ---------------------------------------------------------------------------
# Simple file-backed note store (shared between transport modes)
# ---------------------------------------------------------------------------
DB_FILE = os.path.join(os.path.dirname(__file__), ".test_notes_db.json")


def _load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_db(db: dict) -> None:
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Tools — all preserved from original server
# ---------------------------------------------------------------------------

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
        if query.lower() in n.get("title", "").lower()
        or query.lower() in n.get("content", "").lower()
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


@server.tool(name="health", description="Returns server health and uptime information")
def health() -> dict:
    return {
        "status": "ok",
        "server": "relay-notes-server",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tools": [
            "create_note", "search_notes", "update_note",
            "delete_note", "dangerous_wipe", "health",
        ],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _log(msg: str) -> None:
    """Write diagnostic messages to stderr only — never stdout.

    stdout is owned by the MCP JSON-RPC framing when running in stdio mode.
    Any non-JSON bytes written there corrupt the protocol stream.
    """
    print(msg, file=sys.stderr, flush=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Relay Notes MCP Test Server")
    parser.add_argument(
        "--transport",
        default=None,
        choices=["stdio", "sse", "streamable-http"],
        help=(
            "Transport mode. Defaults to 'stdio' when stdin is not a TTY "
            "(subprocess/pipe), otherwise 'streamable-http'."
        ),
    )
    parser.add_argument(
        "--port", type=int, default=8085,
        help="Listening port for HTTP transports (default: 8085)",
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Bind address for HTTP transports (default: 127.0.0.1)",
    )
    args = parser.parse_args()

    # Auto-detect transport when not explicitly supplied:
    #   • piped stdin (subprocess) → stdio  (test harness invokes this way)
    #   • interactive TTY          → streamable-http
    if args.transport is None:
        args.transport = "stdio" if not sys.stdin.isatty() else "streamable-http"

    _log(f"[mcp_test_server] transport={args.transport}")

    if args.transport == "streamable-http":
        _log(f"[mcp_test_server] Listening on http://{args.host}:{args.port}/mcp")
        server.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            streamable_http_path="/mcp",
        )
    elif args.transport == "sse":
        _log(f"[mcp_test_server] SSE on http://{args.host}:{args.port}")
        server.run(transport="sse", host=args.host, port=args.port)
    elif args.transport == "stdio":
        # stdout is the MCP JSON-RPC pipe — do NOT print anything to it.
        server.run(transport="stdio")
