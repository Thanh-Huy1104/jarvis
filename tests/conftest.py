import pytest
from unittest.mock import MagicMock
import sys
import os

# Add the project root to python path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

@pytest.fixture
def mock_docker_client(mocker):
    """Mocks the docker.from_env() client."""
    mock_client = MagicMock()
    mock_container = MagicMock()
    
    # Setup default container behavior
    mock_container.status = "running"
    mock_container.exec_run.return_value.exit_code = 0
    mock_container.exec_run.return_value.output = (b"OK", b"")
    
    mock_client.containers.get.return_value = mock_container
    
    # Patch docker.from_env to return our mock
    mocker.patch("docker.from_env", return_value=mock_client)
    
    return mock_client, mock_container
