import { useState, useCallback, useRef, useEffect } from "react";
import { Volume2, VolumeX } from "lucide-react";

export type TTSMode = "off" | "click" | "auto";
export type TTSProvider = "web" | "minimax";

import { useTTS as useTTSBase } from "./hooks/useTTS";

export function useTTS() {
  const base = useTTSBase();
  const [mode, setMode] = useState<TTSMode>("click");
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<string>("");
  const [rate, setRate] = useState(1.0);

  useEffect(() => {
    if (typeof window === "undefined" || !(window as any).speechSynthesis) return;
    let attempts = 0;
    const loadVoices = () => {
      let v = (window as any).speechSynthesis.getVoices().filter((v: any) =>
        v.lang.startsWith("de") || v.lang.startsWith("en")
      );
      const google = v.filter((v: any) => v.name.toLowerCase().includes("google"));
      const ms = v.filter((v: any) => v.name.toLowerCase().includes("microsoft"));
      const other = v.filter((v: any) => !v.name.toLowerCase().includes("google") && !v.name.toLowerCase().includes("microsoft"));
      const sorted = [...google, ...ms, ...other];
      setVoices(sorted);
      if (!selectedVoice && sorted.length > 0) {
        const deGoogle = sorted.find((v: any) => v.lang.startsWith("de") && v.name.toLowerCase().includes("google"));
        const de = sorted.find((v: any) => v.lang.startsWith("de"));
        setSelectedVoice(deGoogle ? deGoogle.name : de ? de.name : sorted[0].name);
      }
    };
    loadVoices();
    (window as any).speechSynthesis.onvoiceschanged = loadVoices;
    const interval = setInterval(() => {
      attempts++;
      if ((window as any).speechSynthesis.getVoices().length > 0 || attempts > 10) {
        clearInterval(interval);
        loadVoices();
      }
    }, 300);
    return () => {
      (window as any).speechSynthesis.onvoiceschanged = null;
      clearInterval(interval);
    };
  }, []);

  const speak = useCallback((text: string) => {
    if (mode === "off" || !text.trim()) return;
    if (base.provider === "web") {
      // Bestehende Web-Speech-Logik mit ausgewaehlter Stimme
      if (typeof window === "undefined" || !(window as any).speechSynthesis) return;
      (window as any).speechSynthesis.cancel();
      const cleanText = text.trim().slice(0, 3000);
      const utterance = new SpeechSynthesisUtterance(cleanText);
      const voice = voices.find((v) => v.name === selectedVoice);
      if (voice) utterance.voice = voice;
      utterance.lang = voice?.lang || "de-DE";
      utterance.rate = rate;
      utterance.onstart = () => {};
      utterance.onend = () => {};
      utterance.onerror = () => {};
      (window as any).speechSynthesis.speak(utterance);
    } else {
      base.speak(text);
    }
  }, [base, mode, voices, selectedVoice, rate]);

  const speakText = useCallback((text: string) => {
    speak(text);
  }, [speak]);

  const speakFrom = useCallback((text: string, position: number) => {
    const fromPos = text.slice(position);
    speak(fromPos.slice(0, 3000));
  }, [speak]);

  const stop = useCallback(() => {
    base.stop();
  }, [base]);

  return {
    ...base,
    mode,
    setMode,
    voices,
    selectedVoice,
    setSelectedVoice,
    rate,
    setRate,
    speak,
    speakText,
    speakFrom,
    stop,
  };
}

export function TTSControl({ tts, compact }: { tts: ReturnType<typeof useTTS>; compact?: boolean }) {
  if (compact) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        <select className="input" style={{ width: "auto", fontSize: 10, padding: "2px 6px" }}
          value={tts.mode} onChange={(e) => tts.setMode(e.target.value as TTSMode)}>
          <option value="off">🔇</option>
          <option value="click">👆</option>
          <option value="auto">🔊</option>
        </select>
        <select className="input" style={{ width: "auto", fontSize: 10, padding: "2px 6px" }}
          value={tts.provider} onChange={(e) => tts.setProvider(e.target.value as TTSProvider)}>
          <option value="web">Web</option>
          <option value="minimax">MiniMax</option>
        </select>
        {tts.speaking && (
          <button className="btn" style={{ padding: "2px 6px", fontSize: 10, color: "var(--color-hermes-danger)" }} onClick={tts.stop}>
            ⏹
          </button>
        )}
      </div>
    );
  }

  return (
    <div style={{ padding: "8px 12px", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 12 }}>
      <span style={{ fontWeight: 500 }}>🔊 TTS</span>
      <select className="input" style={{ width: "auto", fontSize: 11, padding: "4px 8px" }}
        value={tts.mode} onChange={(e) => tts.setMode(e.target.value as TTSMode)}>
        <option value="off">Aus</option>
        <option value="click">Beim Klick vorlesen</option>
        <option value="auto">Automatisch vorlesen</option>
      </select>
      <select className="input" style={{ width: "auto", fontSize: 11, padding: "4px 8px" }}
        value={tts.provider} onChange={(e) => tts.setProvider(e.target.value as TTSProvider)}>
        <option value="web">🌐 Browser (Web Speech)</option>
        <option value="minimax">🎙️ MiniMax Cloud TTS</option>
      </select>
      {tts.provider === "web" && (
        <>
          <select className="input" style={{ width: "auto", fontSize: 11, padding: "4px 8px", maxWidth: 250 }}
            value={tts.selectedVoice} onChange={(e) => tts.setSelectedVoice(e.target.value)}>
            {tts.voices.map((v) => {
              const isGoogle = v.name.toLowerCase().includes("google");
              const isMS = v.name.toLowerCase().includes("microsoft");
              const shortName = v.name.replace(/Google\s*/i, "").replace(/Microsoft\s*/i, "").trim();
              return (
                <option key={v.name} value={v.name}>
                  {isGoogle ? "🔊 Google" : isMS ? "🔈 MS" : "🔉"} {shortName} ({v.lang})
                </option>
              );
            })}
            {tts.voices.length === 0 && <option value="">Keine Stimmen verfuegbar</option>}
          </select>
          {tts.voices.length > 0 && !tts.voices.some(v => v.name.toLowerCase().includes("google")) && (
            <div style={{ fontSize: 10, color: "var(--color-hermes-accent-orange)", maxWidth: 220 }}>
              ⚠️ Google Stimmen nicht verfuegbar. Bitte <strong>Chrome Browser</strong> verwenden.<br />
              Edge = Microsoft Stimmen · Chrome = Google Stimmen
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)" }}>Geschw:</span>
            <input type="range" min="0.5" max="2.0" step="0.1" value={tts.rate}
              onChange={(e) => tts.setRate(parseFloat(e.target.value))}
              style={{ width: 60, accentColor: "var(--color-hermes-accent-blue)" }} />
            <span style={{ fontSize: 10, minWidth: 24 }}>{tts.rate.toFixed(1)}x</span>
          </div>
        </>
      )}
      {tts.provider === "minimax" && (
        <div style={{ fontSize: 10, color: "var(--color-hermes-text-secondary)", maxWidth: 220 }}>
          🎙️ Nutzt MiniMax T2A V2 (speech-2.8-hd) ueber das Backend. Audio-URLs sind 24h gueltig.
        </div>
      )}
      {tts.speaking ? (
        <button className="btn" style={{ padding: "4px 10px", fontSize: 11, color: "var(--color-hermes-danger)" }} onClick={tts.stop}>
          ⏹ Stop
        </button>
      ) : (
        <button className="btn" style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => tts.speak("Test der Sprachausgabe im Pi Dashboard 2.0")}>
          ▶️ Test
        </button>
      )}
    </div>
  );
}

export function DynamicTextarea({ value, onChange, placeholder, ...props }: any) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = "auto";
      ref.current.style.height = Math.min(ref.current.scrollHeight, 400) + "px";
    }
  }, [value]);

  return (
    <textarea
      ref={ref}
      className="input"
      value={value}
      onChange={(e) => {
        onChange?.(e);
        if (ref.current) {
          ref.current.style.height = "auto";
          ref.current.style.height = Math.min(ref.current.scrollHeight, 400) + "px";
        }
      }}
      placeholder={placeholder}
      style={{ resize: "none", overflow: "auto", minHeight: 40, maxHeight: 400, fontFamily: "var(--font-mono)", fontSize: 13, lineHeight: 1.5, ...props?.style }}
      {...props}
    />
  );
}
