"""
Docker Sandbox Executor
-----------------------
Executes Python code in an isolated Docker container for security.
"""

import docker
import logging
import time

logger = logging.getLogger(__name__)


class DockerSandbox:
    """
    Manages code execution in a persistent Docker container.
    The container should be started via docker-compose beforehand.
    """
    
    def __init__(self, container_name="jarvis_sandbox"):
        self.container_name = container_name
        self.client = docker.from_env()
        
        try:
            self.container = self.client.containers.get(container_name)
            if self.container.status != "running":
                logger.warning(f"Container '{container_name}' status: {self.container.status}. Attempting to restart...")
                # Force remove and recreate if stuck in restarting state
                try:
                    if self.container.status == "restarting":
                        logger.warning("Container stuck restarting, forcing removal...")
                        self.container.remove(force=True)
                        time.sleep(2)
                        # Recreate from docker-compose
                        logger.info("Container removed, please restart with: docker compose up -d jarvis_sandbox")
                        self.container = None
                        return
                    else:
                        self.container.stop(timeout=5)
                        time.sleep(2)
                        self.container.start()
                        time.sleep(3)  # Give it time to start
                except Exception as e:
                    logger.warning(f"Could not restart container: {e}")
            logger.info(f"Connected to sandbox container: {container_name}")
        except docker.errors.NotFound:
            logger.error(f"Sandbox container '{container_name}' not found. Please run: docker compose up -d")
            self.container = None
        except Exception as e:
            logger.error(f"Failed to connect to sandbox: {e}")
            self.container = None

    def execute(self, code: str, timeout: int = 30) -> str:
        """
        Runs Python code inside the isolated container.
        Returns the combined stdout/stderr.
        
        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            
        Returns:
            Output string (stdout + stderr)
        """
        if not self.container:
            return "Error: Sandbox not connected. Run: docker compose up -d jarvis_sandbox"
        
        # Refresh container status and check if running
        # This handles container recreation scenarios
        try:
            self.container.reload()
            if self.container.status != "running":
                # Try to reconnect by name in case container was recreated
                logger.info(f"Container status is {self.container.status}, attempting to reconnect...")
                try:
                    self.container = self.client.containers.get(self.container_name)
                    self.container.reload()
                    if self.container.status != "running":
                        return f"Error: Container is {self.container.status}, not running. Restart with: docker compose restart jarvis_sandbox"
                except Exception as e:
                    return f"Error: Cannot reconnect to container: {e}"
        except Exception as e:
            # Container might have been recreated, try to reconnect
            logger.info(f"Container reload failed ({e}), attempting to reconnect by name...")
            try:
                self.container = self.client.containers.get(self.container_name)
                self.container.reload()
                if self.container.status != "running":
                    return f"Error: Container is {self.container.status}, not running."
                logger.info(f"Successfully reconnected to {self.container_name}")
            except Exception as reconnect_error:
                return f"Error: Cannot reconnect to container: {reconnect_error}. Run: docker compose up -d jarvis_sandbox"

        # Wrap code to capture exceptions gracefully AND auto-print return values
        # Using string concatenation to avoid f-string nesting issues
        plot_handling = """
    # Auto-encode matplotlib plots if they exist
    plot_files = [f for f in os.listdir('/workspace') if f.endswith('.png') or f.endswith('.jpg')]
    if plot_files:
        for plot_file in plot_files:
            plot_path = f"/workspace/{plot_file}"
            print(f"Plot saved to /workspace/{plot_file}")
            with open(plot_path, 'rb') as f:
                plot_data = base64.b64encode(f.read()).decode('utf-8')
                print(f"[PLOT:{plot_file}]data:image/png;base64,{plot_data}[/PLOT:{plot_file}]")
            # Clean up plot file
            os.remove(plot_path)
"""
        
        wrapped_code = """import sys
import traceback
import os
import base64

try:
""" + self._indent_code(code, spaces=4) + plot_handling + """
except Exception as e:
    print(f"RUNTIME ERROR: {type(e).__name__}: {e}", file=sys.stderr)
    traceback.print_exc()
"""
        
        try:
            # Execute using python -c with proper escaping
            # For production, consider writing to a temp file instead
            result = self.container.exec_run(
                cmd=["python", "-c", wrapped_code],
                workdir="/workspace",
                demux=True,  # Separate stdout and stderr
                environment={"PYTHONUNBUFFERED": "1"}
            )
            
            exit_code = result.exit_code
            stdout = result.output[0].decode("utf-8") if result.output[0] else ""
            stderr = result.output[1].decode("utf-8") if result.output[1] else ""
            
            # Combine outputs
            output = stdout
            if stderr:
                output += f"\n[STDERR]\n{stderr}"
            
            if exit_code != 0:
                return f"⚠️ Execution failed (exit code {exit_code}):\n{output.strip()}"
            
            return output.strip() if output.strip() else "✓ Executed successfully (no output)"
            
        except Exception as e:
            logger.error(f"Sandbox execution error: {e}")
            return f"System Error: {str(e)}"

    def _indent_code(self, code: str, spaces: int = 4) -> str:
        """Helper to indent code for wrapping in try/except"""
        indent = " " * spaces
        return "\n".join(indent + line for line in code.split("\n"))

    def health_check(self) -> bool:
        """
        Verifies the sandbox container is responsive.
        
        Returns:
            True if healthy, False otherwise
        """
        if not self.container:
            return False
        
        try:
            result = self.container.exec_run(
                cmd=["python", "-c", "print('OK')"],
                workdir="/workspace"
            )
            return result.exit_code == 0 and b"OK" in result.output
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def install_package(self, package: str) -> str:
        """
        Installs a Python package in the sandbox using uv.
        
        Args:
            package: Package name (e.g., "pandas", "numpy")
            
        Returns:
            Installation result message
        """
        if not self.container:
            return "Error: Sandbox not connected."
        
        try:
            # Use uv for fast package installation
            result = self.container.exec_run(
                cmd=["uv", "pip", "install", package, "--system"],
                workdir="/workspace"
            )
            
            output = result.output.decode('utf-8') if result.output else ""
            
            if result.exit_code == 0:
                logger.info(f"Installed {package} successfully")
                return f"✓ Installed {package}"
            else:
                logger.error(f"Failed to install {package}: {output}")
                return f"⚠️ Failed to install {package}: {output}"
        except Exception as e:
            logger.error(f"Error installing package {package}: {e}")
            return f"Error installing package: {e}"
    
    def execute_with_packages(self, code: str, timeout: int = 30) -> str:
        """
        Execute code and automatically install missing packages.
        Detects import statements and ensures packages are available.
        
        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            
        Returns:
            Output string (stdout + stderr)
        """
        logger.info("="*50)
        logger.info("SANDBOX EXECUTION WITH PACKAGE DETECTION")
        logger.info("="*50)
        
        # Try to detect required packages from imports
        import re
        import_pattern = r'^(?:from|import)\s+(\w+)'
        imports = re.findall(import_pattern, code, re.MULTILINE)
        
        logger.info(f"Detected imports: {imports}")
        
        # Common package mappings
        package_map = {
            'numpy': 'numpy',
            'np': 'numpy',
            'pandas': 'pandas',
            'pd': 'pandas',
            'matplotlib': 'matplotlib',
            'plt': 'matplotlib',
            'sklearn': 'scikit-learn',
            'cv2': 'opencv-python',
            'requests': 'requests',
            'httpx': 'httpx',
            'boto3': 'boto3',
            'google': 'google-api-python-client',
            'googleapiclient': 'google-api-python-client',
            'psycopg2': 'psycopg2-binary',
            'pymongo': 'pymongo',
            'redis': 'redis',
            'sqlalchemy': 'sqlalchemy',
            'bs4': 'beautifulsoup4',
            'BeautifulSoup': 'beautifulsoup4',
            'duckduckgo_search': 'ddgs',
            'DDGS': 'ddgs',
            'ddgs': 'ddgs',
            'wikipedia': 'wikipedia',
            'playwright': 'playwright',
            'psutil': 'psutil',
            'PIL': 'pillow',
            'yaml': 'pyyaml',
        }
        
        # Install common scientific packages if detected
        packages_to_install = set()
        for imp in imports:
            if imp in package_map:
                packages_to_install.add(package_map[imp])
        
        if packages_to_install:
            logger.info(f"Installing packages: {packages_to_install}")
            for pkg in packages_to_install:
                logger.info(f"  Installing {pkg}...")
                install_result = self.install_package(pkg)
                logger.info(f"  {install_result}")
        else:
            logger.info("No packages need to be installed")
        
        # Now execute the code
        logger.info("Starting code execution...")
        result = self.execute(code, timeout)
        logger.info(f"Execution complete. Result length: {len(result)} chars")
        logger.info("="*50)
        return result
