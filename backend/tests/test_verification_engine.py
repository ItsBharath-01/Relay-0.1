import pytest
from app.verification.engine import verification_engine

@pytest.mark.asyncio
async def test_web_search_verification_pass():
    params = {"query": "FastAPI tutorial"}
    result = {
        "query": "FastAPI tutorial",
        "result_count": 2,
        "results": [
            {"title": "FastAPI Tutorial", "url": "https://fastapi.tiangolo.com/tutorial/", "snippet": "Learn FastAPI"},
            {"title": "FastAPI GitHub", "url": "https://github.com/tiangolo/fastapi", "snippet": "FastAPI framework"}
        ]
    }
    ver = await verification_engine.verify_task_outcome("web_search", "web_search", params, result)
    assert ver.result == "passed"
    assert ver.evidence["result_count"] == 2
    assert "FastAPI Tutorial" in ver.evidence["top_title"]


@pytest.mark.asyncio
async def test_web_search_verification_fail_empty():
    params = {"query": "Nonexistent search query 12345"}
    result = {"query": "Nonexistent", "result_count": 0, "results": []}
    ver = await verification_engine.verify_task_outcome("web_search", "web_search", params, result)
    assert ver.result == "failed"

@pytest.mark.asyncio
async def test_web_reader_verification_pass():
    params = {"url": "https://example.com"}
    result = {
        "url": "https://example.com",
        "status_code": 200,
        "title": "Example Domain",
        "content": "Example Domain: This domain is established to be used for illustrative examples in documents.",
        "char_count": 95
    }
    ver = await verification_engine.verify_task_outcome("web_read", "web_read", params, result)
    assert ver.result == "passed"
    assert ver.evidence["char_count"] == 95

@pytest.mark.asyncio
async def test_document_summarize_verification():
    params = {"text": "Long source text..."}
    result = {
        "summary": "This is a comprehensive summary of the input text highlighting key points.",
        "char_count": 75
    }
    ver = await verification_engine.verify_task_outcome("document_summarize", "document_summarize", params, result)
    assert ver.result == "passed"
    assert ver.evidence["summary_char_count"] > 20


@pytest.mark.asyncio
async def test_browser_media_playback_not_verifiable_without_player_state():
    """Rule 6: browser navigation for music/media cannot claim success without active player state."""
    params = {"url": "https://music.example.com", "action": "play_song"}
    result = {"url": "https://music.example.com", "status_code": 200, "title": "Music Site", "char_count": 500}
    ver = await verification_engine.verify_task_outcome("browser_navigate", "play_song", params, result)
    assert ver.result == "not_verifiable"
    assert "player_state" in ver.evidence


@pytest.mark.asyncio
async def test_browser_media_playback_passed_with_active_player_state():
    """Rule 6: active player state confirms playback."""
    params = {"url": "https://music.example.com", "action": "play_song"}
    result = {"url": "https://music.example.com", "status_code": 200, "title": "Music Site", "player_state": "playing"}
    ver = await verification_engine.verify_task_outcome("browser_navigate", "play_song", params, result)
    assert ver.result == "passed"
    assert ver.evidence["player_state"] == "playing"

