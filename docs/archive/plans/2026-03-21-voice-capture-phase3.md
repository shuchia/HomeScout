# Voice Capture (Phase 3) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add voice note capture with Whisper transcription and post-tour reminders to the touring pipeline.

**Architecture:** Audio files are uploaded to S3 via multipart endpoint, then a Celery task calls OpenAI Whisper API for async transcription. For Pro users, transcription chains into Claude note enhancement (already built in Phase 2). Frontend uses the MediaRecorder API for hold-to-talk recording with a pulsing indicator, and polls for transcription status.

**Tech Stack:** OpenAI Whisper API (transcription), S3 (audio storage), Celery (async tasks), MediaRecorder API (browser recording), existing Claude enhance_note endpoint (Pro chaining)

---

## Prerequisites

- Phase 1 complete: tour_notes table exists with `source`, `audio_s3_key`, `transcription_status` columns
- Phase 2 complete: `enhance_note` Claude endpoint exists for Pro auto-enhancement
- S3 bucket configured (`S3_BUCKET_NAME` env var)
- Redis running (Celery broker)
- New env var needed: `OPENAI_API_KEY`
- New dependency: `openai` Python package

## Existing Infrastructure

| What | Where | Relevance |
|------|-------|-----------|
| S3 upload pattern | `app/services/storage/photo_service.py` | Reuse `_get_s3_client()` pattern, same bucket |
| Celery app | `app/celery_app.py` | Add new task module + beat schedule entry |
| Notes endpoint | `app/routers/tours.py:760` | `POST /api/tours/{id}/notes` creates typed notes — voice endpoint is parallel |
| tour_notes schema | `supabase/migrations/005_tour_pipeline.sql` | Already has `source`, `audio_s3_key`, `transcription_status` columns |
| Note enhancement | `app/services/claude_service.py` | `enhance_note()` method — chain after transcription for Pro users |
| Tour types | `frontend/types/tour.ts` | `TourNote` already has `source: 'voice' | 'typed'` and `transcription_status` |

---

### Task 19: Whisper API Integration Service

**Files:**
- Create: `backend/app/services/transcription/whisper_service.py`
- Create: `backend/app/services/transcription/__init__.py`
- Modify: `backend/requirements.txt` (add `openai`)
- Test: `backend/tests/test_whisper_service.py`

**What this does:** A service that takes an audio file (bytes or S3 key), sends it to OpenAI Whisper API, and returns the transcription text. Handles downloading from S3 if given a key.

**Implementation:**

```python
# backend/app/services/transcription/whisper_service.py
import os
import logging
from io import BytesIO

from openai import OpenAI

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

_openai_client = None

def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


class WhisperService:
    @staticmethod
    def transcribe(audio_data: bytes, filename: str = "audio.webm") -> str:
        """Transcribe audio bytes using OpenAI Whisper API.

        Args:
            audio_data: Raw audio file bytes
            filename: Filename hint for format detection (e.g., "audio.webm", "note.m4a")

        Returns:
            Transcribed text string

        Raises:
            ValueError: If audio_data is empty
            Exception: If Whisper API call fails
        """
        if not audio_data:
            raise ValueError("Empty audio data")

        client = _get_openai_client()

        audio_file = BytesIO(audio_data)
        audio_file.name = filename

        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",
        )

        return response.strip()

    @staticmethod
    def transcribe_from_s3(s3_key: str) -> str:
        """Download audio from S3 and transcribe it.

        Uses the same S3 client pattern as PhotoService.
        """
        from app.services.storage.photo_service import _get_s3_client, S3_BUCKET

        s3 = _get_s3_client()
        response = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)
        audio_data = response["Body"].read()

        # Extract filename from S3 key for format hint
        filename = s3_key.split("/")[-1] if "/" in s3_key else s3_key

        return WhisperService.transcribe(audio_data, filename)
```

**Tests (4 tests):**
1. `test_transcribe_success` — mock OpenAI client, verify transcription returned
2. `test_transcribe_empty_audio_raises` — verify ValueError for empty bytes
3. `test_transcribe_from_s3` — mock S3 download + OpenAI, verify end-to-end
4. `test_transcribe_strips_whitespace` — verify trailing whitespace removed

**Dependency:** Add `openai>=1.0.0` to `requirements.txt`

**Commit:** `feat: add Whisper API integration service for voice transcription`

---

### Task 20: Voice Upload Endpoint + Celery Transcription Task

**Files:**
- Create: `backend/app/tasks/transcription_tasks.py`
- Modify: `backend/app/celery_app.py` (add task module to includes)
- Modify: `backend/app/routers/tours.py` (add voice upload endpoint)
- Modify: `backend/app/schemas.py` (add VoiceNoteResponse schema)
- Test: `backend/tests/test_tours.py` (add voice endpoint tests)

**What this does:**
1. A new endpoint `POST /api/tours/{tour_id}/notes/voice` that accepts multipart audio upload
2. Uploads audio to S3 at `tours/{user_id}/{tour_id}/voice/{uuid}.{ext}`
3. Creates a `tour_notes` row with `source="voice"`, `transcription_status="pending"`
4. Dispatches a Celery task to transcribe asynchronously
5. Returns 202 Accepted with the note ID

The Celery task:
1. Calls `WhisperService.transcribe_from_s3(s3_key)`
2. Updates `tour_notes.content` with transcription text
3. Sets `transcription_status="complete"` (or "failed" on error)
4. If Pro user: chains `enhance_note` task (Task 21)

**Endpoint:**

```python
@router.post("/api/tours/{tour_id}/notes/voice", status_code=202)
async def create_voice_note(
    tour_id: str,
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
):
    """Upload audio for voice note. Returns 202 — transcription happens async."""
```

- Max file size: 5 MB (voice notes are short)
- Allowed content types: `audio/webm`, `audio/mp4`, `audio/m4a`, `audio/mpeg`, `audio/wav`, `audio/ogg`
- Upload to S3, create DB row, dispatch Celery task, return 202

**Celery task:**

```python
# backend/app/tasks/transcription_tasks.py
from app.celery_app import celery_app

@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def transcribe_voice_note(self, note_id: str, s3_key: str, user_id: str, tour_id: str):
    """Transcribe a voice note using Whisper API."""
    # 1. Call WhisperService.transcribe_from_s3(s3_key)
    # 2. Update tour_notes: set content, transcription_status="complete"
    # 3. On failure: set transcription_status="failed", retry if retries remaining
```

**Schemas:**

```python
class VoiceNoteResponse(BaseModel):
    id: str
    source: str  # "voice"
    transcription_status: str  # "pending"
    audio_s3_key: str
    created_at: str
```

**Tests (3 tests):**
1. `test_voice_upload_requires_auth` — 401 without auth
2. `test_voice_upload_creates_pending_note` — mock S3 + Celery, verify 202 + pending status
3. `test_voice_upload_rejects_oversized_file` — 400 for > 5MB

**Celery config:** Add `"app.tasks.transcription_tasks"` to `celery_app` includes list.

**Commit:** `feat: add voice note upload endpoint with async Celery transcription`

---

### Task 21: AI Auto-Enhancement Chained After Transcription (Pro)

**Files:**
- Modify: `backend/app/tasks/transcription_tasks.py` (chain enhance after transcribe)
- Modify: `backend/app/services/tier_service.py` (no changes needed — already has `get_user_tier`)
- Test: `backend/tests/test_transcription_tasks.py`

**What this does:** After Whisper transcription completes for a Pro user, automatically call the existing `ClaudeService.enhance_note()` to clean up the text and suggest tags. Save the enhanced text alongside the raw transcription.

**Implementation changes to `transcribe_voice_note` task:**

```python
@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def transcribe_voice_note(self, note_id: str, s3_key: str, user_id: str, tour_id: str):
    """Transcribe voice note, then auto-enhance for Pro users."""
    try:
        # 1. Transcribe
        text = WhisperService.transcribe_from_s3(s3_key)

        # 2. Save raw transcription
        supabase_admin.table("tour_notes").update({
            "content": text,
            "transcription_status": "complete",
        }).eq("id", note_id).execute()

        # 3. Check if Pro → auto-enhance
        import asyncio
        tier = asyncio.get_event_loop().run_until_complete(
            TierService.get_user_tier(user_id)
        )
        if tier == "pro":
            enhance_voice_note.delay(note_id, text, tour_id)

    except Exception as exc:
        supabase_admin.table("tour_notes").update({
            "transcription_status": "failed",
        }).eq("id", note_id).execute()
        raise self.retry(exc=exc)


@celery_app.task(max_retries=1)
def enhance_voice_note(note_id: str, raw_text: str, tour_id: str):
    """Auto-enhance a transcribed voice note using Claude (Pro only)."""
    # 1. Fetch apartment context from tour
    # 2. Call ClaudeService.enhance_note(raw_text, apartment_context)
    # 3. Save enhanced_text to a new field or append to content
    # For now: update content with enhanced text, keep raw as a prefix comment
```

**Note:** The `tour_notes` table doesn't have an `enhanced_text` column. For simplicity, store the enhanced version in `content` — the raw transcription is preserved in the audio recording itself. If we want both versions later, we can add a column.

**Tests (3 tests):**
1. `test_transcribe_task_success` — mock Whisper, verify content saved + status=complete
2. `test_transcribe_task_failure_sets_failed` — mock Whisper to raise, verify status=failed
3. `test_pro_user_chains_enhancement` — mock tier as pro, verify enhance task dispatched

**Commit:** `feat: chain AI note enhancement after voice transcription for Pro users`

---

### Task 22: Frontend Hold-to-Talk Component

**Files:**
- Create: `frontend/components/VoiceCapture.tsx`
- Modify: `frontend/lib/api.ts` (add `uploadVoiceNote` function)
- Modify: `frontend/app/tours/[id]/page.tsx` (add VoiceCapture to Capture tab)

**What this does:** A mobile-first hold-to-talk button that records audio using the browser's MediaRecorder API, then uploads it to the voice note endpoint.

**VoiceCapture component:**

```typescript
interface VoiceCaptureProps {
  tourId: string
  onNoteCreated: () => void  // callback to refresh notes list
}
```

**Behavior:**
1. User presses and holds the button
2. Red pulsing dot + duration timer appears
3. MediaRecorder captures audio (WebM/Opus format)
4. User releases
5. Audio blob is uploaded via `uploadVoiceNote(tourId, audioBlob)`
6. Note appears in list with "Transcribing..." status
7. Parent component polls for transcription completion

**Key implementation details:**
- Use `navigator.mediaDevices.getUserMedia({ audio: true })` for mic access
- Use `MediaRecorder` API with `mimeType: 'audio/webm;codecs=opus'` (fallback to `audio/webm`)
- On touch devices: use `onTouchStart`/`onTouchEnd` for press-and-hold
- On desktop: use `onMouseDown`/`onMouseUp`
- Handle permission denied gracefully (show message)
- Minimum recording duration: 0.5 seconds (discard shorter)
- Maximum recording duration: 120 seconds (auto-stop)

**API function:**

```typescript
export async function uploadVoiceNote(tourId: string, audioBlob: Blob): Promise<{ note: TourNote }> {
  const authHeaders = getAuthHeaders()
  const formData = new FormData()
  formData.append('file', audioBlob, 'voice-note.webm')

  const response = await fetch(`${API_URL}/api/tours/${tourId}/notes/voice`, {
    method: 'POST',
    headers: authHeaders,  // No Content-Type — browser sets multipart boundary
    body: formData,
  })
  if (!response.ok) throw new ApiError('Failed to upload voice note', response.status)
  return response.json()
}
```

**UI layout:**

```
┌────────────────────────┐
│    Hold to Record      │   ← Big button, centered
│    🎙️ 0:00             │   ← Mic icon + timer (shown while recording)
└────────────────────────┘
```

While recording:
- Button turns red with pulsing animation
- Timer counts up (MM:SS)
- "Release to stop" text

**Commit:** `feat: add VoiceCapture hold-to-talk component with MediaRecorder`

---

### Task 23: Frontend Transcription Polling + Status Display

**Files:**
- Modify: `frontend/app/tours/[id]/page.tsx` (add polling logic + voice note display)
- Modify: `frontend/types/tour.ts` (add `audio_url` to TourNote if not present)

**What this does:** After a voice note is uploaded, the UI shows "Transcribing..." and polls the notes endpoint every 2 seconds until the transcription is complete.

**Polling logic:**

```typescript
// In the tour detail page, after a voice note is created:
useEffect(() => {
  const pendingNotes = tour?.notes?.filter(n => n.transcription_status === 'pending')
  if (!pendingNotes?.length) return

  const interval = setInterval(async () => {
    // Re-fetch tour to get updated note statuses
    const { tour: updated } = await getTour(tourId)
    setTour(updated)

    // Stop polling when no more pending
    const stillPending = updated.notes?.filter(n => n.transcription_status === 'pending')
    if (!stillPending?.length) clearInterval(interval)
  }, 2000)

  return () => clearInterval(interval)
}, [tour?.notes])
```

**Voice note display in notes list:**

```tsx
{note.source === 'voice' && (
  <div className="flex items-center gap-2">
    <span className="text-blue-500">🎤</span>
    {note.transcription_status === 'pending' ? (
      <span className="text-gray-400 italic animate-pulse">Transcribing...</span>
    ) : note.transcription_status === 'failed' ? (
      <span className="text-red-500 text-sm">Transcription failed</span>
    ) : (
      <p className="text-gray-700">{note.content}</p>
    )}
  </div>
)}
```

**Audio playback:** If the note has an `audio_s3_key`, show a small play button that uses a presigned URL. The backend already generates presigned URLs for S3 keys. Add an `audio_url` field to the notes list response (generate presigned URL for voice notes).

**Commit:** `feat: add transcription polling and voice note status display`

---

### Task 24: Post-Tour Push Notification (Celery Scheduled Task)

**Files:**
- Create: `backend/app/tasks/tour_reminder_tasks.py`
- Modify: `backend/app/celery_app.py` (add beat schedule + task include)
- Test: `backend/tests/test_tour_reminder_tasks.py`

**What this does:** A Celery beat task that runs every 10 minutes, finds tours where `scheduled_time` was 30 minutes ago and the tour hasn't been marked as toured yet, and creates a notification in the `notifications` table prompting the user to rate their tour.

**Note:** True push notifications (PWA/service workers) are out of scope for this task. Instead, we create a `notification` record in Supabase that the frontend can poll or display via a notification bell. The design doc mentions push notifications, but in-app notifications are the practical first step.

**Implementation:**

```python
# backend/app/tasks/tour_reminder_tasks.py
from datetime import datetime, timezone, timedelta
from app.celery_app import celery_app
from app.services.tier_service import supabase_admin

@celery_app.task
def check_tour_reminders():
    """Check for tours that ended ~30 min ago and create reminder notifications."""
    if not supabase_admin:
        return

    now = datetime.now(timezone.utc)
    reminder_window_start = now - timedelta(minutes=35)
    reminder_window_end = now - timedelta(minutes=25)
    today = now.date().isoformat()

    # Find scheduled tours for today that haven't been toured yet
    result = supabase_admin.table("tour_pipeline") \
        .select("id, user_id, apartment_id, scheduled_date, scheduled_time") \
        .eq("scheduled_date", today) \
        .eq("stage", "scheduled") \
        .execute()

    for tour in (result.data or []):
        scheduled_time = tour.get("scheduled_time")
        if not scheduled_time:
            continue

        # Parse and check if in reminder window
        # Create notification if in window
        supabase_admin.table("notifications").insert({
            "user_id": tour["user_id"],
            "type": "tour_reminder",
            "title": "How was your tour?",
            "message": f"Just toured {tour['apartment_id']}? Tap to rate and capture your impressions.",
            "apartment_id": tour["apartment_id"],
        }).execute()
```

**Beat schedule:** Add to `celery_app.py`:

```python
"check_tour_reminders": {
    "task": "app.tasks.tour_reminder_tasks.check_tour_reminders",
    "schedule": crontab(minute="*/10"),  # Every 10 minutes
},
```

**Tests (3 tests):**
1. `test_creates_reminder_for_recent_tour` — mock Supabase with a tour 30 min ago, verify notification created
2. `test_skips_already_toured` — tour in "toured" stage, no notification
3. `test_skips_tours_without_time` — tour with no scheduled_time, no notification

**Commit:** `feat: add post-tour reminder notifications via Celery beat`

---

### Task 25: Backend + E2E Tests for Voice

**Files:**
- Create/Modify: `backend/tests/test_transcription_tasks.py` (if not created in Task 21)
- Modify: `frontend/e2e/tours.spec.ts` (add voice capture E2E tests)

**Backend tests (consolidated from earlier tasks, ensure these exist):**
1. Whisper service: transcribe success, empty audio rejection, S3 integration
2. Voice upload endpoint: auth required, creates pending note, file size validation
3. Transcription task: success saves content, failure sets status, Pro chains enhancement
4. Tour reminder: creates notification, skips toured, skips no-time

**E2E tests (4 tests):**

1. **Voice capture button visible on capture tab**
   - Navigate to tour detail, click Capture tab
   - Verify "Hold to Record" or voice capture button exists

2. **Voice note shows transcribing status**
   - Mock voice upload endpoint returning pending note
   - Mock notes list with a pending voice note
   - Verify "Transcribing..." text appears

3. **Transcription completes and shows text**
   - First poll returns pending, second returns complete with content
   - Verify transcription text appears after polling

4. **Voice note shows mic icon**
   - Mock a completed voice note in tour data
   - Verify mic icon / voice indicator appears (vs pencil for typed)

**Commit:** `test: add backend and E2E tests for voice capture pipeline`

---

## Environment Variables (New)

```bash
# Required for Phase 3
OPENAI_API_KEY=sk-...        # OpenAI API key for Whisper transcription
```

## Dependencies (New)

```
openai>=1.0.0                 # OpenAI Python SDK for Whisper API
```

## Migration Notes

No new Supabase migrations needed — the `tour_notes` table already has `source`, `audio_s3_key`, and `transcription_status` columns from Phase 1's `005_tour_pipeline.sql`.

## Task Dependencies

```
Task 19 (Whisper service)
    ↓
Task 20 (Voice endpoint + Celery task)
    ↓
Task 21 (Auto-enhancement chaining)

Task 22 (Frontend VoiceCapture)  ← depends on Task 20 (needs endpoint)
    ↓
Task 23 (Polling + display)      ← depends on Task 22

Task 24 (Tour reminders)         ← independent

Task 25 (Tests)                  ← depends on all above
```

Tasks 19→20→21 are sequential (backend pipeline).
Task 22→23 are sequential (frontend pipeline).
Task 24 is independent.
Task 25 is last.
