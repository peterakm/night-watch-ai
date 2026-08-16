let ctx: AudioContext | null = null;

function getContext(): AudioContext {
  if (!ctx) {
    ctx = new AudioContext();
  }
  return ctx;
}

/** A short two-tone alert chime, synthesized so no audio asset is needed. */
export function playAlertChime(): void {
  try {
    const audioCtx = getContext();
    const now = audioCtx.currentTime;

    [880, 660].forEach((freq, i) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      const start = now + i * 0.16;
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(0.2, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, start + 0.16);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(start);
      osc.stop(start + 0.18);
    });
  } catch {
    // Audio isn't critical to the app working; ignore if the browser blocks it
    // (e.g. no user gesture yet) or AudioContext is unavailable.
  }
}
