# Story 20.9: Voice Input (Speech-to-Text)

Status: drafted

## Story

As a user,
I want to speak to Annie using my microphone,
so that I can communicate hands-free or when typing is inconvenient.

## Acceptance Criteria

1. Microphone button visible in input area
2. Click to start/stop recording
3. Visual feedback while recording (pulsing icon, waveform)
4. Real-time transcription displayed as user speaks
5. Auto-stop after 3 seconds of silence
6. Manual stop and send option
7. Browser compatibility check (Chrome, Edge, Safari)
8. Graceful fallback for unsupported browsers (hide mic button)
9. Permission handling for microphone access
10. Error handling (permission denied, no microphone)
11. Language detection or configuration

## Tasks / Subtasks

- [ ] Task 1: Create useSpeechRecognition hook (AC: 1, 2, 4, 5, 6)
  - [ ] 1.1 Create `web/src/lib/hooks/useSpeechRecognition.ts`
  - [ ] 1.2 Initialize Web Speech API
  - [ ] 1.3 Handle start/stop recording
  - [ ] 1.4 Process interim and final results
  - [ ] 1.5 Implement silence detection for auto-stop

- [ ] Task 2: Create VoiceInput component (AC: 1, 3)
  - [ ] 2.1 Create `web/src/components/chat/VoiceInput.tsx`
  - [ ] 2.2 Add microphone button with states
  - [ ] 2.3 Add pulsing animation while recording
  - [ ] 2.4 Optional: Add waveform visualization

- [ ] Task 3: Handle browser compatibility (AC: 7, 8)
  - [ ] 3.1 Detect Web Speech API support
  - [ ] 3.2 Hide button on unsupported browsers
  - [ ] 3.3 Show tooltip explaining unsupported

- [ ] Task 4: Handle permissions (AC: 9, 10)
  - [ ] 4.1 Request microphone permission
  - [ ] 4.2 Handle permission denied gracefully
  - [ ] 4.3 Show helpful error for no microphone
  - [ ] 4.4 Remember permission state

- [ ] Task 5: Integrate with InputArea
  - [ ] 5.1 Add VoiceInput button to input area
  - [ ] 5.2 Connect transcription to textarea
  - [ ] 5.3 Allow editing before send

- [ ] Task 6: Add language configuration (AC: 11)
  - [ ] 6.1 Default to browser language
  - [ ] 6.2 Allow manual language selection
  - [ ] 6.3 Store preference in localStorage

## Dev Notes

### Web Speech API Usage

```typescript
const useSpeechRecognition = () => {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  const isSupported = 'SpeechRecognition' in window || 'webkitSpeechRecognition' in window;

  useEffect(() => {
    if (!isSupported) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();

    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      let interimTranscript = '';
      let finalTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      setTranscript(finalTranscript || interimTranscript);
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
    };

    recognitionRef.current = recognition;
  }, [isSupported]);

  const startListening = () => {
    recognitionRef.current?.start();
    setIsListening(true);
  };

  const stopListening = () => {
    recognitionRef.current?.stop();
    setIsListening(false);
  };

  return { isSupported, isListening, transcript, startListening, stopListening };
};
```

### Browser Support Matrix

| Browser | Support | Notes |
|---------|---------|-------|
| Chrome | Full | Best support |
| Edge | Full | Chromium-based |
| Safari | Full | iOS 14.5+ |
| Firefox | Limited | Needs flag/polyfill |

### VoiceInput Component

```tsx
export function VoiceInput({ onTranscript }: { onTranscript: (text: string) => void }) {
  const { isSupported, isListening, transcript, startListening, stopListening } = useSpeechRecognition();

  useEffect(() => {
    if (transcript) {
      onTranscript(transcript);
    }
  }, [transcript, onTranscript]);

  if (!isSupported) {
    return null; // Hide on unsupported browsers
  }

  return (
    <button
      onClick={isListening ? stopListening : startListening}
      className={cn(
        "p-2 rounded-full transition-colors",
        isListening
          ? "bg-red-500 text-white animate-pulse"
          : "hover:bg-gray-100 dark:hover:bg-gray-800"
      )}
      title={isListening ? "Stop recording" : "Start voice input"}
    >
      <Mic className="w-5 h-5" />
    </button>
  );
}
```

### Permission Handling

```typescript
const requestMicPermission = async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach(track => track.stop()); // Release immediately
    return true;
  } catch (error) {
    if (error.name === 'NotAllowedError') {
      toast.error('Microphone permission denied');
    } else if (error.name === 'NotFoundError') {
      toast.error('No microphone found');
    }
    return false;
  }
};
```

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.9]
- [MDN Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API)

## Dev Agent Record

### Context Reference

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
