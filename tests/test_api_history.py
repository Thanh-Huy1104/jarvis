
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from app.main import app
from app.core.types import ChatMessage
import pytest

@pytest.fixture
def mock_chat_history():
    mock = AsyncMock()
    # Mock get_history to return a fixed list
    mock.get_history.return_value = [
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Hi there!")
    ]
    return mock

def test_get_history_endpoint(mock_chat_history):
    # Override the chat_history in app state
    app.state.chat_history = mock_chat_history
    
    client = TestClient(app)
    session_id = "test-session-123"
    
    response = client.get(f"/history/{session_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["role"] == "user"
    assert data[0]["content"] == "Hello"
    assert data[1]["role"] == "assistant"
    assert data[1]["content"] == "Hi there!"
    
    # Verify adapter was called
    mock_chat_history.get_history.assert_called_with(session_id=session_id)
