import pytest
from app.execution.sandbox import DockerSandbox

class TestDockerSandbox:
    
    def test_initialization_success(self, mock_docker_client):
        client, container = mock_docker_client
        sandbox = DockerSandbox(container_name="jarvis_sandbox")
        
        assert sandbox.container is not None
        client.containers.get.assert_called_with("jarvis_sandbox")

    def test_initialization_failure(self, mocker):
        # Simulate docker exception
        mocker.patch("docker.from_env", side_effect=Exception("Docker down"))
        sandbox = DockerSandbox()
        assert sandbox.container is None

    def test_execute_success(self, mock_docker_client):
        client, container = mock_docker_client
        # Mock successful execution
        container.exec_run.return_value.exit_code = 0
        container.exec_run.return_value.output = (b"Hello World", b"")
        
        sandbox = DockerSandbox()
        result = sandbox.execute("print('Hello World')")
        
        assert "Hello World" in result
        assert "⚠️" not in result

    def test_execute_runtime_error(self, mock_docker_client):
        client, container = mock_docker_client
        # Mock execution failure (exit code 1)
        container.exec_run.return_value.exit_code = 1
        container.exec_run.return_value.output = (b"", b"SyntaxError: invalid syntax")
        
        sandbox = DockerSandbox()
        result = sandbox.execute("invalid code")
        
        assert "⚠️ Execution failed" in result
        assert "SyntaxError" in result

    def test_install_package(self, mock_docker_client):
        client, container = mock_docker_client
        container.exec_run.return_value.exit_code = 0
        container.exec_run.return_value.output = b"Successfully installed pandas"
        
        sandbox = DockerSandbox()
        result = sandbox.install_package("pandas")
        
        assert "✓ Installed pandas" in result
        # Check if uv was used
        call_args = container.exec_run.call_args
        assert "uv" in call_args[1]['cmd'] or "uv" in call_args[0][0]

    def test_execute_with_packages_detection(self, mock_docker_client):
        client, container = mock_docker_client
        sandbox = DockerSandbox()
        
        # We need to spy on install_package to verify it's called
        # But since it's a method on the instance, we can just check the docker calls
        
        code = """
import pandas as pd
import requests
print("ok")
        """
        
        sandbox.execute_with_packages(code)
        
        # Verify calls to exec_run. 
        # Expected: install pandas (mapped check), install requests, then execute code
        # Note: 'pandas' isn't in the default map in sandbox.py? Let's check sandbox.py content again if needed.
        # Actually I saw 'cv2', 'requests' etc in the map. 'pandas' might not be there.
        # Let's check a mapped one like 'cv2' -> 'opencv-python'
        
        code_mapped = "import cv2\nprint('image')"
        sandbox.execute_with_packages(code_mapped)
        
        # We expect a call to install 'opencv-python'
        # Filter calls to find the installation command
        install_calls = [
            call for call in container.exec_run.call_args_list 
            if "uv" in (call[1].get('cmd') or call[0][0])
        ]
        
        # Flatten the args to find the package name
        installed_packages = []
        for call in install_calls:
            cmd = call[1].get('cmd') or call[0][0]
            # cmd is list like ['uv', 'pip', 'install', 'opencv-python', '--system']
            if 'opencv-python' in cmd:
                installed_packages.append('opencv-python')
                
        assert 'opencv-python' in installed_packages
