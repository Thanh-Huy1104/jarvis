#!/usr/bin/env python3
"""
Mobile API Test Script
----------------------
Quick tests for the mobile endpoints
"""

import asyncio
import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/mobile"
TEST_USER = "test_user_123"


def test_health():
    """Test health check"""
    print("Testing health check...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"✓ Health: {response.json()}")
    return response.status_code == 200


def test_create_section():
    """Test creating a note section"""
    print("\nTesting section creation...")
    response = requests.post(
        f"{BASE_URL}/notes/sections",
        json={
            "user_id": TEST_USER,
            "name": "Work",
            "description": "Work-related notes"
        }
    )
    data = response.json()
    print(f"✓ Created section: {data}")
    return data.get("id")


def test_get_sections():
    """Test getting sections"""
    print("\nTesting get sections...")
    response = requests.get(f"{BASE_URL}/notes/sections/{TEST_USER}")
    data = response.json()
    print(f"✓ Sections: {data}")
    return data.get("sections", [])


def test_create_note(section_id):
    """Test creating a note"""
    print("\nTesting note creation...")
    response = requests.post(
        f"{BASE_URL}/notes",
        json={
            "user_id": TEST_USER,
            "section_name": "Work",
            "content": "This is a test note from the mobile API",
            "tags": ["test", "mobile"]
        }
    )
    data = response.json()
    print(f"✓ Created note: {data}")
    return data.get("id")


def test_get_notes_by_section(section_id):
    """Test getting notes by section"""
    print(f"\nTesting get notes by section {section_id}...")
    response = requests.get(f"{BASE_URL}/notes/{TEST_USER}/section/{section_id}")
    data = response.json()
    print(f"✓ Notes in section: {len(data.get('notes', []))} notes")
    return data.get("notes", [])


def test_create_reminder():
    """Test creating a calendar reminder"""
    print("\nTesting reminder creation...")
    tomorrow = datetime.now() + timedelta(days=1)
    tomorrow_3pm = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0)
    
    response = requests.post(
        f"{BASE_URL}/calendar/events",
        json={
            "user_id": TEST_USER,
            "title": "Test Reminder",
            "datetime": tomorrow_3pm.isoformat(),
            "description": "This is a test reminder",
            "duration_minutes": 30
        }
    )
    data = response.json()
    print(f"✓ Created reminder: {data}")
    return data.get("id")


def test_get_calendar_events():
    """Test getting calendar events"""
    print("\nTesting get calendar events...")
    response = requests.get(f"{BASE_URL}/calendar/events/{TEST_USER}")
    data = response.json()
    print(f"✓ Calendar events: {len(data.get('events', []))} events")
    return data.get("events", [])


def test_voice_to_action_text():
    """Test voice-to-action with text input"""
    print("\nTesting voice-to-action (text)...")
    response = requests.post(
        f"{BASE_URL}/voice-to-action",
        json={
            "user_id": TEST_USER,
            "text": "Remind me to buy groceries tomorrow at 5pm"
        }
    )
    data = response.json()
    print(f"✓ Intent: {data.get('intent')}")
    print(f"  Confidence: {data.get('confidence')}")
    print(f"  Result: {data.get('result')}")
    return data


def test_search_notes():
    """Test note search"""
    print("\nTesting note search...")
    response = requests.get(f"{BASE_URL}/notes/{TEST_USER}/search?q=test")
    data = response.json()
    print(f"✓ Search results: {len(data.get('notes', []))} notes found")
    return data.get("notes", [])


def run_tests():
    """Run all tests"""
    print("=" * 60)
    print("Mobile API Test Suite")
    print("=" * 60)
    
    try:
        # Health check
        if not test_health():
            print("❌ Server not responding!")
            return
        
        # Section tests
        section_id = test_create_section()
        sections = test_get_sections()
        
        # Note tests
        if section_id:
            note_id = test_create_note(section_id)
            notes = test_get_notes_by_section(section_id)
            search_results = test_search_notes()
        
        # Calendar tests
        reminder_id = test_create_reminder()
        events = test_get_calendar_events()
        
        # Voice-to-action test
        voice_result = test_voice_to_action_text()
        
        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Cannot connect to server at", BASE_URL)
        print("Make sure the server is running: uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n❌ Error during tests: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_tests()
