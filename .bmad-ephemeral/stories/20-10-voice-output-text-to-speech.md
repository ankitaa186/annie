# Story 20.10: Voice Output (Text-to-Speech)

Status: drafted

## Story

As a user,
I want Annie to speak her responses aloud,
so that I can listen to her while doing other things or for a more natural conversation feel.

## Acceptance Criteria

1. Play button on each Annie message
2. Global auto-play toggle (off by default)
3. Voice selection from available browser voices
4. Speed control (0.5x - 2x)
5. Pause/resume playback
6. Visual indicator during playback
7. Stop playback when new message arrives
8. Keyboard shortcut for play/pause (Space when message focused)
9. Remember voice preferences (localStorage)
10. Graceful handling of TTS unavailability

## Tasks / Subtasks

- [ ] Task 1: Create useTextToSpeech hook (AC: 1, 3, 4, 5)
  - [ ] 1.1 Create `web/src/lib/hooks/useTextToSpeech.ts`
  - [ ] 1.2 Initialize Web Speech Synthesis API
  - [ ] 1.3 Implement speak/pause/resume/stop
  - [ ] 1.4 Handle voice selection
  - [ ] 1.5 Handle rate adjustment

- [ ] Task 2: Create VoiceOutput component (AC: 1, 6)
  - [ ] 2.1 Create `web/src/components/chat/VoiceOutput.tsx`
  - [ ] 2.2 Add play/pause button per message
  - [ ] 2.3 Show visual indicator during speech
  - [ ] 2.4 Add progress indicator (optional)

- [ ] Task 3: Create voice settings UI (AC: 2, 3, 4, 9)
  - [ ] 3.1 Add voice settings to preferences
  - [ ] 3.2 Voice dropdown with available voices
  - [ ] 3.3 Speed slider (0.5x - 2x)
  - [ ] 3.4 Auto-play toggle
  - [ ] 3.5 Persist settings to localStorage

- [ ] Task 4: Handle playback interactions (AC: 5, 7, 8)
  - [ ] 4.1 Implement pause/resume toggle
  - [ ] 4.2 Stop on new message arrival
  - [ ] 4.3 Add keyboard shortcut support

- [ ] Task 5: Integrate with AnnieMessage
  - [ ] 5.1 Add VoiceOutput to message component
  - [ ] 5.2 Connect to global settings
  - [ ] 5.3 Handle auto-play if enabled

- [ ] Task 6: Handle errors (AC: 10)
  - [ ] 6.1 Detect TTS support
  - [ ] 6.2 Hide features if unsupported
  - [ ] 6.3 Show fallback message

## Dev Notes

### Web Speech Synthesis API

```typescript
const useTextToSpeech = () => {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<SpeechSynthesisVoice | null>(null);
  const [rate, setRate] = useState(1);

  const isSupported = 'speechSynthesis' in window;

  useEffect(() => {
    if (!isSupported) return;

    const loadVoices = () => {
      const availableVoices = speechSynthesis.getVoices();
      setVoices(availableVoices);
      // Default to first English voice
      const englishVoice = availableVoices.find(v => v.lang.startsWith('en'));
      setSelectedVoice(englishVoice || availableVoices[0]);
    };

    loadVoices();
    speechSynthesis.onvoiceschanged = loadVoices;
  }, [isSupported]);

  const speak = (text: string) => {
    if (!isSupported || !selectedVoice) return;

    // Cancel any ongoing speech
    speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice = selectedVoice;
    utterance.rate = rate;

    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);

    speechSynthesis.speak(utterance);
  };

  const pause = () => {
    speechSynthesis.pause();
    setIsPaused(true);
  };

  const resume = () => {
    speechSynthesis.resume();
    setIsPaused(false);
  };

  const stop = () => {
    speechSynthesis.cancel();
    setIsSpeaking(false);
    setIsPaused(false);
  };

  return {
    isSupported,
    isSpeaking,
    isPaused,
    voices,
    selectedVoice,
    rate,
    setSelectedVoice,
    setRate,
    speak,
    pause,
    resume,
    stop,
  };
};
```

### VoiceOutput Component

```tsx
export function VoiceOutput({ text }: { text: string }) {
  const { isSupported, isSpeaking, isPaused, speak, pause, resume, stop } = useTextToSpeech();

  if (!isSupported) {
    return null;
  }

  const handleClick = () => {
    if (isSpeaking && !isPaused) {
      pause();
    } else if (isPaused) {
      resume();
    } else {
      speak(text);
    }
  };

  return (
    <button
      onClick={handleClick}
      className={cn(
        "p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors",
        isSpeaking && "text-purple-500"
      )}
      title={isSpeaking ? "Pause" : "Listen"}
    >
      {isSpeaking && !isPaused ? (
        <Pause className="w-4 h-4" />
      ) : (
        <Volume2 className="w-4 h-4" />
      )}
    </button>
  );
}
```

### Voice Settings UI

```tsx
export function VoiceSettings() {
  const { voices, selectedVoice, setSelectedVoice, rate, setRate } = useVoiceSettings();
  const [autoPlay, setAutoPlay] = useLocalStorage('annie-autoplay-voice', false);

  return (
    <div className="space-y-4 p-4">
      <div>
        <label className="text-sm font-medium">Voice</label>
        <select
          value={selectedVoice?.name}
          onChange={(e) => {
            const voice = voices.find(v => v.name === e.target.value);
            setSelectedVoice(voice || null);
          }}
          className="w-full mt-1 border rounded px-2 py-1"
        >
          {voices.map(voice => (
            <option key={voice.name} value={voice.name}>
              {voice.name} ({voice.lang})
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-sm font-medium">Speed: {rate}x</label>
        <input
          type="range"
          min="0.5"
          max="2"
          step="0.1"
          value={rate}
          onChange={(e) => setRate(parseFloat(e.target.value))}
          className="w-full mt-1"
        />
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="autoplay"
          checked={autoPlay}
          onChange={(e) => setAutoPlay(e.target.checked)}
        />
        <label htmlFor="autoplay" className="text-sm">
          Auto-play Annie's responses
        </label>
      </div>
    </div>
  );
}
```

### Stop on New Message

```typescript
// In message thread or streaming handler
useEffect(() => {
  // Stop TTS when new message arrives
  if (newMessageArrived) {
    speechSynthesis.cancel();
  }
}, [messages.length]);
```

### Complementary to Home Assistant

This web TTS complements Epic 16's Home Assistant voice output:
- Web TTS: User at computer, listening through browser
- HA TTS: User away from computer, voice through smart speakers

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.10]
- [MDN Speech Synthesis API](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis)

## Dev Agent Record

### Context Reference

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
