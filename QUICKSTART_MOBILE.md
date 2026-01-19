# Mobile API - Quick Start Guide

## 🚀 What Changed?

Your backend now has **simplified mobile-focused endpoints** for voice-based reminders and notes!

### New Features Added:
1. ✅ **Calendar/Reminders** - Voice-based event creation
2. ✅ **Notes with Sections** - Organized note-taking  
3. ✅ **Voice-to-Action** - Complete audio → intent → action pipeline
4. ✅ **Smart Section Management** - Asks before creating new sections
5. ✅ **Mobile REST API** - All endpoints under `/mobile/*`

## 📁 New Files Created

```
app/
├── db/                         # NEW: Database layer
│   ├── __init__.py
│   ├── session.py             # Database setup
│   └── models.py              # Calendar & Notes models
├── mobile/                     # NEW: Mobile API package
│   ├── __init__.py
│   ├── skills.py              # Fixed calendar & note functions
│   ├── intent_classifier.py  # LLM-based intent classification
│   └── routes.py              # Mobile API endpoints
└── main.py                     # Updated to include mobile routes

docs/
└── MOBILE_API.md              # Complete API documentation

test_mobile_api.py              # Test script
```

## 🔧 Setup

### 1. Install New Dependency

```bash
pip install python-dateutil
```

### 2. Database Initialization

The database tables will auto-create on first run. Make sure PostgreSQL is running:

```bash
# Check if PostgreSQL is running
docker-compose up -d postgres  # if using docker-compose

# Or check your local PostgreSQL
psql -U jarvis -d jarvis_db -c "SELECT 1"
```

### 3. Start the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Test the API

```bash
# Run the test script
python test_mobile_api.py
```

## 🎯 Quick Examples

### Example 1: Voice to Reminder

**Request:**
```bash
curl -X POST "http://localhost:8000/mobile/voice-to-action" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "text": "Remind me to call mom tomorrow at 3pm"
  }'
```

**Response:**
```json
{
  "transcribed_text": "Remind me to call mom tomorrow at 3pm",
  "intent": "create_reminder",
  "confidence": 0.95,
  "result": {
    "success": true,
    "data": {
      "id": 1,
      "title": "Call mom",
      "event_datetime": "2026-01-19T15:00:00",
      "duration_minutes": 30
    },
    "message": "Reminder created: Call mom at January 19 at 03:00 PM"
  }
}
```

### Example 2: Voice to Note with Section

**Request:**
```bash
curl -X POST "http://localhost:8000/mobile/voice-to-action" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "text": "Add to my work notes: follow up with John about the presentation"
  }'
```

**If section exists:**
```json
{
  "intent": "create_note",
  "result": {
    "success": true,
    "message": "Note added to Work"
  }
}
```

**If section doesn't exist:**
```json
{
  "intent": "create_note",
  "result": {
    "success": false,
    "needs_section_creation": true,
    "section_name": "Work",
    "clarification_question": "The section 'Work' doesn't exist. Would you like to create it?",
    "pending_data": {
      "content": "Follow up with John about the presentation",
      "tags": ["work", "follow-up"]
    }
  }
}
```

**Then confirm section creation:**
```bash
curl -X POST "http://localhost:8000/mobile/notes/sections/confirm" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "section_name": "Work",
    "description": "Work-related notes",
    "pending_note_data": {
      "content": "Follow up with John about the presentation",
      "tags": ["work", "follow-up"]
    }
  }'
```

### Example 3: Get Calendar Events

```bash
# Get all events
curl "http://localhost:8000/mobile/calendar/events/user123"

# Get events for a date range
curl "http://localhost:8000/mobile/calendar/events/user123?start_date=2026-01-19T00:00:00&end_date=2026-01-20T00:00:00"
```

### Example 4: Upload Audio File

```bash
curl -X POST "http://localhost:8000/mobile/voice-to-text" \
  -F "audio=@recording.wav"
```

## 📱 Mobile App Integration (Expo)

### Install Dependencies

```bash
npm install expo-av expo-file-system
```

### Simple Voice Recording Example

```typescript
import { Audio } from 'expo-av';
import * as FileSystem from 'expo-file-system';

async function recordAndSend() {
  // 1. Request permissions
  await Audio.requestPermissionsAsync();
  await Audio.setAudioModeAsync({
    allowsRecordingIOS: true,
    playsInSilentModeIOS: true,
  });

  // 2. Start recording
  const { recording } = await Audio.Recording.createAsync(
    Audio.RecordingOptionsPresets.HIGH_QUALITY
  );
  
  // ... user speaks ...
  
  // 3. Stop recording
  await recording.stopAndUnloadAsync();
  const uri = recording.getURI();
  
  // 4. Convert to base64
  const base64 = await FileSystem.readAsStringAsync(uri, {
    encoding: FileSystem.EncodingType.Base64,
  });
  
  // 5. Send to backend
  const response = await fetch('http://YOUR_IP:8000/mobile/voice-to-action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: 'user123',
      audio_base64: base64,
    }),
  });
  
  const result = await response.json();
  
  // 6. Handle result
  if (result.result.needs_section_creation) {
    // Show dialog to confirm section creation
    Alert.alert(
      'Create Section?',
      result.result.clarification_question,
      [
        { text: 'Cancel', style: 'cancel' },
        { 
          text: 'Create', 
          onPress: () => confirmSectionCreation(
            result.result.section_name,
            result.result.pending_data
          )
        }
      ]
    );
  } else if (result.result.success) {
    Alert.alert('Success', result.result.message);
  }
}
```

## 🔄 Main Differences from Original Jarvis

| Aspect | Original Jarvis | Mobile Version |
|--------|----------------|----------------|
| **Skills** | Dynamic code generation | Fixed, predefined functions |
| **Learning** | Autonomous skill learning | No learning |
| **API** | WebSocket streaming | REST endpoints |
| **Complexity** | Full LAM with verification | Simple intent → action |
| **Focus** | General-purpose agent | Reminders + Notes only |

## 📊 Database Tables

The mobile API adds 3 new tables:

```sql
calendar_events     -- Reminders/events
note_sections       -- Note categories
notes               -- User notes
```

These work alongside your existing `chat_sessions` and `chat_messages` tables.

## 🎨 Frontend UI Suggestions

### Main Screen
- **Voice Button** (center, large) → triggers recording
- **Quick Views:**
  - Today's reminders (top)
  - Recent notes (middle)
  - All sections (bottom tabs)

### After Voice Input
1. Show transcribed text
2. Show intent + confidence
3. If needs clarification → show dialog
4. Otherwise → show success + result

### Calendar View
- Day/Week/Month views
- Swipe to delete
- Tap to edit

### Notes View
- Sections as tabs or categories
- Search bar
- Swipe to delete
- Tap to view/edit

## 🐛 Troubleshooting

### Server won't start
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill process if needed
kill -9 <PID>
```

### Database connection error
```bash
# Check PostgreSQL is running
docker-compose ps

# Check connection string in .env
cat .env | grep DATABASE_URL
```

### Intent classification not working
- Check LLM is loaded and responding
- Review logs: `tail -f logs/app.log`
- Test with simple inputs first

### Audio transcription fails
- Check Whisper model is downloaded
- Verify audio format (prefer WAV, 16kHz, mono)
- Check GPU availability: `nvidia-smi`

## 📚 Next Steps

1. **Test the API** - Run `python test_mobile_api.py`
2. **Read full docs** - See `docs/MOBILE_API.md`
3. **Build mobile app** - Use the Expo examples above
4. **Add features** - Push notifications, recurring reminders, etc.

## 🤝 Need Help?

- Full API docs: `docs/MOBILE_API.md`
- Test script: `test_mobile_api.py`
- Example requests: See MOBILE_API.md

---

**Your backend is now mobile-ready! 🎉**
