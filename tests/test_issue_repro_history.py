
from fastapi.testclient import TestClient
from app.main import app
import pytest

# We use the real app, which connects to the real DB in this environment.
# This is an integration test.

def test_get_specific_history():
    session_id = "3d2abe1f-0689-40c2-8e2c-040cebb8ff50"
    
    with TestClient(app) as client:
        response = client.get(f"/history/{session_id}")
        
        if response.status_code != 200:
            print(f"FAILED: Status code {response.status_code}")
            print(f"Response: {response.text}")
            assert response.status_code == 200
            
        data = response.json()
        print(f"Success! Received {len(data)} messages.")
        
        # Verify structure
        assert isinstance(data, list)
        if len(data) > 0:
            first_msg = data[0]
            assert "role" in first_msg
            assert "content" in first_msg
            print("First message sample:", first_msg)
        else:
            print("Warning: History is empty (but request succeeded).")

if __name__ == "__main__":
    test_get_specific_history()
