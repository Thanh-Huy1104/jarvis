# Mobile API Implementation

This is a simplified, mobile-focused implementation of the Jarvis backend for voice-based reminders and notes.

## Features

### 1. Voice Reminders (Calendar Events)
- Create reminders with natural language: "Remind me to buy groceries tomorrow at 5pm"
- View upcoming events by date range
- Update and delete reminders
- Automatic datetime parsing from natural language

### 2. Voice Notes with Sections
- Create notes organized into sections (categories)
- Automatic section detection: "Add to my work notes..."
- Intelligent section creation workflow (asks before creating new sections)
- Search notes by content
- Tag support for better organization

### 3. Voice-to-Action Pipeline
- Single endpoint that handles: audio → text → intent → action
- Powered by Whisper STT and LLM-based intent classification
- Returns structured results ready for mobile UI

## Architecture

```
Mobile App (Expo/React Native)
    ↓
FastAPI Backend (/mobile/*)
    ↓
┌─────────────────────────────────────┐
│  Voice Processing Pipeline          │
│  1. STT (Whisper) → Text            │
│  2. Intent Classifier (LLM) → JSON  │
│  3. Fixed Skills → Database         │
└─────────────────────────────────────┘
    ↓
PostgreSQL
```

### Key Differences from Main Jarvis

| Feature | Main Jarvis | Mobile Version |
|---------|-------------|----------------|
| Skills | Dynamic code generation | Fixed, predefined functions |
| Learning | Autonomous skill learning | No learning, static skills |
| Complexity | Full LAM with verification loops | Simple intent → action |
| Use Case | General-purpose agent | Focused: reminders + notes |
| API | WebSocket streaming | REST + WebSocket |

## API Endpoints

### Voice Processing

#### POST `/mobile/voice-to-text`
Upload audio file, get transcribed text.

**Request:**
```
multipart/form-data
- audio: File
```

**Response:**
```json
{
  "success": true,
  "text": "Remind me to call John tomorrow at 3pm",
  "filename": "audio.wav"
}
```

#### POST `/mobile/voice-to-action`
Complete voice processing pipeline (recommended for mobile apps).

**Request:**
```json
{
  "user_id": "user123",
  "text": "Remind me to call John tomorrow at 3pm",
  "audio_base64": null  // Optional: base64 encoded audio
}
```

**Response:**
```json
{
  "transcribed_text": "Remind me to call John tomorrow at 3pm",
  "intent": "create_reminder",
  "confidence": 0.95,
  "result": {
    "success": true,
    "data": {
      "id": 1,
      "title": "Call John",
      "event_datetime": "2026-01-19T15:00:00",
      "duration_minutes": 30
    },
    "message": "Reminder created: Call John at January 19 at 03:00 PM"
  }
}
```

**Special case - Section doesn't exist:**
```json
{
  "result": {
    "success": false,
    "needs_section_creation": true,
    "section_name": "Work",
    "clarification_question": "The section 'Work' doesn't exist. Would you like to create it?",
    "pending_data": {
      "content": "Follow up with the presentation",
      "tags": ["work", "follow-up"]
    }
  }
}
```

### Calendar/Reminders

#### POST `/mobile/calendar/events`
Create a reminder/event.

**Request:**
```json
{
  "user_id": "user123",
  "title": "Call John",
  "datetime": "2026-01-19T15:00:00",
  "description": "Discuss project timeline",
  "duration_minutes": 30
}
```

#### GET `/mobile/calendar/events/{user_id}`
Get events for a user.

**Query params:**
- `start_date`: ISO datetime (optional)
- `end_date`: ISO datetime (optional)
- `limit`: Max results (default: 50)

**Response:**
```json
{
  "events": [
    {
      "id": 1,
      "title": "Call John",
      "description": "Discuss project timeline",
      "event_datetime": "2026-01-19T15:00:00",
      "duration_minutes": 30,
      "created_at": "2026-01-18T10:30:00"
    }
  ]
}
```

#### PUT `/mobile/calendar/events/{event_id}`
Update an event.

#### DELETE `/mobile/calendar/events/{event_id}?user_id=user123`
Delete an event.

### Note Sections

#### POST `/mobile/notes/sections`
Create a note section.

**Request:**
```json
{
  "user_id": "user123",
  "name": "Work",
  "description": "Work-related notes"
}
```

#### GET `/mobile/notes/sections/{user_id}`
Get all sections.

**Response:**
```json
{
  "sections": [
    {
      "id": 1,
      "name": "Work",
      "description": "Work-related notes",
      "created_at": "2026-01-18T10:00:00"
    },
    {
      "id": 2,
      "name": "Personal",
      "description": null,
      "created_at": "2026-01-18T10:05:00"
    }
  ]
}
```

#### POST `/mobile/notes/sections/confirm`
Confirm section creation (used after voice intent asks to create).

**Request:**
```json
{
  "user_id": "user123",
  "section_name": "Work",
  "description": "Work-related notes",
  "pending_note_data": {
    "content": "Follow up with presentation",
    "tags": ["work", "follow-up"]
  }
}
```

### Notes

#### POST `/mobile/notes`
Create a note.

**Request:**
```json
{
  "user_id": "user123",
  "section_name": "Work",
  "content": "Meeting notes from standup",
  "tags": ["meeting", "standup"]
}
```

#### GET `/mobile/notes/{user_id}/section/{section_id}`
Get notes in a section.

#### GET `/mobile/notes/{user_id}/search?q=meeting`
Search notes by content.

#### DELETE `/mobile/notes/{note_id}?user_id=user123`
Delete a note.

## Database Schema

```sql
-- Calendar Events
CREATE TABLE calendar_events (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    description TEXT,
    event_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    duration_minutes INTEGER DEFAULT 60,
    metadata JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Note Sections
CREATE TABLE note_sections (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Notes
CREATE TABLE notes (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR NOT NULL,
    section_id INTEGER REFERENCES note_sections(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    tags JSON,
    metadata JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## Setup & Installation

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Configure database:**
Ensure PostgreSQL is running and update `.env`:
```env
DATABASE_URL=postgresql+asyncpg://jarvis:jarvis_password@localhost:5432/jarvis_db
```

3. **Initialize database:**
Tables are auto-created on first run via SQLAlchemy.

4. **Run the server:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Mobile App Integration (Expo/React Native)

### Example: Voice Recording & Processing

```typescript
import * as FileSystem from 'expo-file-system';
import { Audio } from 'expo-av';

async function recordAndProcess() {
  // 1. Record audio
  const recording = await Audio.Recording.createAsync(
    Audio.RecordingOptionsPresets.HIGH_QUALITY
  );
  
  // ... user records ...
  
  await recording.stopAndUnloadAsync();
  const uri = recording.getURI();
  
  // 2. Upload to backend
  const formData = new FormData();
  formData.append('audio', {
    uri: uri,
    type: 'audio/wav',
    name: 'recording.wav',
  });
  
  const response = await fetch('http://YOUR_SERVER:8000/mobile/voice-to-action', {
    method: 'POST',
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    body: JSON.stringify({
      user_id: 'user123',
      text: null,  // Will be transcribed from audio
      audio_base64: await FileSystem.readAsStringAsync(uri, {
        encoding: FileSystem.EncodingType.Base64,
      }),
    }),
  });
  
  const result = await response.json();
  
  // 3. Handle result
  if (result.result.needs_section_creation) {
    // Show dialog: "Create section 'Work'?"
    showSectionCreationDialog(result.result.section_name, result.result.pending_data);
  } else if (result.result.success) {
    // Show success message
    showSuccess(result.result.message);
  }
}
```

### Example: Create Reminder from Text

```typescript
async function createReminder(text: string, userId: string) {
  const response = await fetch('http://YOUR_SERVER:8000/mobile/voice-to-action', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      user_id: userId,
      text: text,
    }),
  });
  
  const result = await response.json();
  return result;
}

// Usage
const result = await createReminder("Remind me to buy groceries tomorrow at 5pm", "user123");
```

### Example: Get Calendar Events

```typescript
async function getEvents(userId: string, startDate?: Date, endDate?: Date) {
  const params = new URLSearchParams({
    start_date: startDate?.toISOString() || '',
    end_date: endDate?.toISOString() || '',
  });
  
  const response = await fetch(
    `http://YOUR_SERVER:8000/mobile/calendar/events/${userId}?${params}`
  );
  
  const data = await response.json();
  return data.events;
}

// Get today's events
const today = new Date();
const endOfDay = new Date(today);
endOfDay.setHours(23, 59, 59);

const todayEvents = await getEvents("user123", today, endOfDay);
```

## Intent Classification Examples

The LLM-based intent classifier can understand various natural language inputs:

### Reminders
- "Remind me to call mom tomorrow at 3pm"
- "Set a reminder for the dentist appointment next Monday at 9am"
- "I need to remember to submit the report by Friday 5pm"

### Notes
- "Note that the meeting went well"
- "Add to my work notes: follow up with the client"
- "Save this in personal: buy groceries and clean the house"
- "Create a note in Ideas: mobile app for plant care"

### View Calendar
- "What do I have scheduled tomorrow?"
- "Show me my calendar for this week"
- "What's on my schedule today?"

### View Notes
- "Show me my work notes"
- "Search my notes for meeting"
- "What sections do I have?"

## Testing

```bash
# Test voice-to-text
curl -X POST "http://localhost:8000/mobile/voice-to-text" \
  -F "audio=@test_audio.wav"

# Test voice-to-action with text
curl -X POST "http://localhost:8000/mobile/voice-to-action" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "text": "Remind me to buy groceries tomorrow at 5pm"
  }'

# Create a section
curl -X POST "http://localhost:8000/mobile/notes/sections" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "name": "Work",
    "description": "Work-related notes"
  }'

# Get sections
curl "http://localhost:8000/mobile/notes/sections/test_user"

# Get calendar events
curl "http://localhost:8000/mobile/calendar/events/test_user"
```

## Performance Considerations

- **STT (Whisper)**: Uses faster-whisper with GPU acceleration
- **Intent Classification**: Single LLM call per request
- **Database**: PostgreSQL with proper indexes on user_id and datetime fields
- **Concurrency**: Async/await throughout for handling multiple requests

## Future Enhancements

- [ ] Push notifications for upcoming reminders
- [ ] Recurring reminders support
- [ ] Note sharing between users
- [ ] Voice playback of notes and reminders
- [ ] Offline support with sync
- [ ] Multiple language support
- [ ] Calendar integration (Google Calendar, iCal)
- [ ] Rich text/markdown notes
- [ ] Image/file attachments to notes

## Troubleshooting

**STT not working:**
- Check if Whisper model is downloaded
- Verify GPU availability: `nvidia-smi`
- Check audio format (prefer WAV 16kHz mono)

**Intent classification issues:**
- Review LLM logs for parsing errors
- Check if datetime parsing is working correctly
- Verify user input is clear and specific

**Database errors:**
- Ensure PostgreSQL is running
- Check database connection string in `.env`
- Verify tables are created: `psql -d jarvis_db -c "\dt"`

## License

MIT
