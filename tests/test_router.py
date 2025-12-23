import pytest
from unittest.mock import MagicMock
from app.core.router import JarvisRouter

class TestJarvisRouter:
    
    @pytest.fixture
    def mock_llm(self, mocker):
        # Mock ChatOpenAI class
        mock_cls = mocker.patch("app.core.router.ChatOpenAI")
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        return mock_instance

    def test_initialization(self, mock_llm):
        router = JarvisRouter()
        assert router.llm is not None
        
    def test_classify_speed(self, mock_llm):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.content = "speed"
        mock_llm.invoke.return_value = mock_response
        
        router = JarvisRouter()
        result = router.classify("hello")
        
        assert result == "speed"
        mock_llm.invoke.assert_called_once()
        
    def test_classify_complex(self, mock_llm):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.content = "complex"
        mock_llm.invoke.return_value = mock_response
        
        router = JarvisRouter()
        result = router.classify("calculate pi")
        
        assert result == "complex"
        
    def test_classify_fallback_on_unclear(self, mock_llm):
        # Setup mock response with weird output
        mock_response = MagicMock()
        mock_response.content = "I'm not sure"
        mock_llm.invoke.return_value = mock_response
        
        router = JarvisRouter()
        result = router.classify("something ambiguous")
        
        # Should default to complex
        assert result == "complex"

    def test_classify_fallback_on_error(self, mock_llm):
        # Setup mock to raise exception
        mock_llm.invoke.side_effect = Exception("LLM Error")
        
        router = JarvisRouter()
        result = router.classify("test")
        
        # Should default to complex
        assert result == "complex"

    def test_context_inclusion(self, mock_llm):
        mock_response = MagicMock()
        mock_response.content = "complex"
        mock_llm.invoke.return_value = mock_response
        
        router = JarvisRouter()
        router.classify("follow up", conversation_context="User: Hi\nAI: Hello")
        
        # Check that context was included in the prompt
        args, _ = mock_llm.invoke.call_args
        prompt = args[0]
        assert "User: Hi" in prompt
        assert "AI: Hello" in prompt
