# 🚀 Quick Setup Guide - Mobile Voice Assistant

This project is now **mobile-only** with a clean backend and Expo app.

## ✅ What Changed

### Backend (Simplified)
- ❌ Removed: Autonomous skill learning, code generation, complex nodes
- ✅ Kept: Voice-to-text (Whisper), Intent classification (LLM), Database, Mobile API
- 📦 Archived unused files to `archive/` folder

### Frontend (New)
- ✅ Created: Complete Expo React Native app in `mobile-app/`
- ✅ Features: Voice recording, calendar, notes with sections
- ✅ All UI screens ready to use

## 🏃 Quick Start

### 1. Start Backend

```bash
# Install dependency (if not already)
pip install python-dateutil

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be at: `http://localhost:8000`

### 2. Start Mobile App

```bash
# Go to mobile app folder
cd mobile-app

# Install dependencies (if not already)
npm install

# Start Expo
npm start
```

Then:
- Press `i` for iOS Simulator
- Press `a` for Android Emulator  
- Or scan QR code with Expo Go on your phone

### 3. Configure API URL (Important!)

**For iOS Simulator:**
- Already configured to use `localhost:8000` ✅

**For Android Emulator:**
Edit `mobile-app/src/config/api.ts`:
```typescript
BASE_URL: 'http://10.0.2.2:8000'
```

**For Physical Device:**
1. Find your computer's IP: `ipconfig getifaddr en0` (macOS) or `ipconfig` (Windows)
2. Edit `mobile-app/src/config/api.ts`:
```typescript
BASE_URL: 'http://YOUR_IP:8000'  // e.g., http://192.168.1.100:8000
```

## 📱 Using the App

### Voice Commands

Tap and hold the 🎤 button, then speak:

**Create Reminders:**
- "Remind me to buy groceries tomorrow at 5pm"
- "Set a reminder for the dentist next Monday at 9am"

**Create Notes:**
- "Note that the meeting went well"
- "Add to my work notes: follow up with client"
- "Save this in personal: weekend plans"

**View Data:**
- "What do I have scheduled tomorrow?"
- "Show me my work notes"

### Navigation

- **Home Tab** 🎤 - Voice recording (main feature)
- **Calendar Tab** 📅 - View/delete reminders
- **Notes Tab** 📝 - View notes by section, create sections

## 🗂️ Project Structure

```
jarvis/
├── app/
│   ├── adapters/        # STT, LLM, database adapters
│   ├── db/              # Database models (NEW)
│   ├── mobile/          # Mobile API endpoints (NEW)
│   ├── domain/          # Ports/interfaces
│   └── main.py          # Simplified FastAPI app
├── archive/             # Archived code (not used)
├── mobile-app/          # Expo React Native app (NEW)
│   ├── src/
│   │   ├── config/      # API configuration
│   │   ├── services/    # API client
│   │   ├── screens/     # UI screens
│   │   └── types/       # TypeScript types
│   └── App.tsx          # Main app with navigation
├── docker-compose.yml
└── requirements.txt
```

## 🔧 Troubleshooting

### Backend won't start
```bash
# Check PostgreSQL is running
docker-compose up -d

# Check port 8000 is free
lsof -i :8000
```

### Mobile app can't connect
1. Check backend is running: Open `http://localhost:8000/mobile/health` in browser
2. For physical device, make sure phone and computer are on same WiFi
3. Update `BASE_URL` in `mobile-app/src/config/api.ts`

### Voice recording not working
- iOS Simulator doesn't support microphone - use physical device
- Grant microphone permissions when prompted

## 📚 Documentation

- **Mobile App**: `mobile-app/README.md`
- **API Reference**: `docs/MOBILE_API.md`
- **Architecture**: `docs/ARCHITECTURE_COMPARISON.md`

## 🎯 What's Working

✅ Voice-to-text transcription (Whisper)  
✅ Intent classification (LLM)  
✅ Calendar/Reminders CRUD  
✅ Notes with Sections  
✅ Smart section creation (asks for confirmation)  
✅ Mobile app with 3 screens  
✅ Tab navigation  
✅ Swipe to delete  

## 🚀 Next Steps

1. **Test voice recording** - Main feature!
2. **Create some reminders** - Try different voice commands
3. **Organize notes** - Create sections and add notes
4. **Customize** - Update colors, add features, etc.

## 📦 Dependencies

### Backend
- FastAPI, Uvicorn
- Whisper (STT)
- vLLM/OpenAI (LLM)
- PostgreSQL
- SQLAlchemy

### Mobile
- React Native (Expo)
- React Navigation
- expo-av (audio recording)
- TypeScript

## 🎨 Customization

### Change Colors
Edit styles in each screen file (`mobile-app/src/screens/*.tsx`)

### Add Features
- Add more screens in `mobile-app/src/screens/`
- Add routes in `mobile-app/App.tsx`
- Add API methods in `mobile-app/src/services/api.ts`

### Backend Endpoints
All mobile endpoints are in `app/mobile/routes.py`

---

**Your mobile voice assistant is ready! 🎉**

Start both backend and mobile app, then tap the 🎤 button to begin!
