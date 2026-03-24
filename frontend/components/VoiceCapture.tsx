'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { uploadVoiceNote } from '@/lib/api'

interface VoiceCaptureProps {
  tourId: string
  onNoteCreated: () => void
}

type CaptureState = 'idle' | 'recording' | 'uploading'

const MAX_DURATION_SECONDS = 120
const MIN_DURATION_SECONDS = 0.5

export default function VoiceCapture({ tourId, onNoteCreated }: VoiceCaptureProps) {
  const [state, setState] = useState<CaptureState>('idle')
  const [duration, setDuration] = useState(0)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const startTimeRef = useRef<number>(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop())
      }
    }
  }, [])

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const startRecording = useCallback(async () => {
    setErrorMsg(null)

    // Check browser support
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      setErrorMsg('Voice recording not supported in this browser.')
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // Pick a supported mimeType
      let mimeType = 'audio/webm;codecs=opus'
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = 'audio/webm'
      }

      const recorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = async () => {
        // Stop all tracks
        stream.getTracks().forEach((t) => t.stop())
        streamRef.current = null

        const elapsed = (Date.now() - startTimeRef.current) / 1000

        if (elapsed < MIN_DURATION_SECONDS) {
          setErrorMsg('Recording too short. Hold longer to record.')
          setState('idle')
          setDuration(0)
          return
        }

        const blob = new Blob(chunksRef.current, { type: mimeType })
        setState('uploading')
        setDuration(0)

        try {
          await uploadVoiceNote(tourId, blob)
          onNoteCreated()
        } catch {
          setErrorMsg('Failed to upload voice note. Please try again.')
        } finally {
          setState('idle')
        }
      }

      recorder.start(250) // collect data every 250ms
      startTimeRef.current = Date.now()
      setState('recording')
      setDuration(0)

      // Duration timer
      timerRef.current = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000)
        setDuration(elapsed)
        if (elapsed >= MAX_DURATION_SECONDS) {
          stopRecording()
        }
      }, 250)
    } catch (err: unknown) {
      // Permission denied or other error
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        setErrorMsg('Microphone access required. Please allow microphone permissions.')
      } else {
        setErrorMsg('Could not start recording. Please try again.')
      }
    }
  }, [tourId, onNoteCreated, stopRecording])

  const handlePointerDown = useCallback(() => {
    if (state === 'idle') startRecording()
  }, [state, startRecording])

  const handlePointerUp = useCallback(() => {
    if (state === 'recording') stopRecording()
  }, [state, stopRecording])

  const formatDuration = (seconds: number): string => {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${m}:${String(s).padStart(2, '0')}`
  }

  if (state === 'uploading') {
    return (
      <div className="bg-gray-100 border-2 border-gray-300 rounded-xl p-6 text-center min-h-[80px] flex items-center justify-center">
        <div className="flex items-center gap-2 text-gray-500">
          <svg className="h-5 w-5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm font-medium">Uploading...</span>
        </div>
      </div>
    )
  }

  if (state === 'recording') {
    return (
      <div
        className="bg-red-50 border-2 border-red-400 rounded-xl p-6 text-center min-h-[80px] select-none touch-none cursor-pointer"
        onMouseUp={handlePointerUp}
        onMouseLeave={handlePointerUp}
        onTouchEnd={handlePointerUp}
        onTouchCancel={handlePointerUp}
      >
        <div className="flex flex-col items-center gap-1">
          <div className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 rounded-full bg-red-500 animate-pulse" />
            <span className="text-sm font-medium text-red-700">
              Recording... {formatDuration(duration)}
            </span>
          </div>
          <span className="text-xs text-red-500">Release to stop</span>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div
        className="bg-gray-100 border-2 border-gray-300 rounded-xl p-6 text-center min-h-[80px] flex items-center justify-center cursor-pointer select-none touch-none hover:bg-gray-150 active:bg-gray-200 transition-colors"
        onMouseDown={handlePointerDown}
        onTouchStart={handlePointerDown}
        role="button"
        tabIndex={0}
        aria-label="Hold to record voice note"
      >
        <div className="flex items-center gap-2 text-gray-600">
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
          <span className="text-sm font-medium">Hold to Record</span>
        </div>
      </div>
      {errorMsg && (
        <p className="text-xs text-red-500 mt-2 text-center">{errorMsg}</p>
      )}
    </div>
  )
}
