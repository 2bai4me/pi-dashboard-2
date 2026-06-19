// useTTS.ts — Text-to-Speech Hook (Web Speech API + MiniMax Backend)
// User-Direktive 17.06.2026: TTS-Funktion fuer Beschreibung und Empfehlung.
// Erweitert 19.06.2026: MiniMax T2A V2 via Backend.

import { useState, useRef, useCallback } from "react"
import { api } from "../api"

export type TTSProvider = "web" | "minimax"

export function useTTS() {
  const [speaking, setSpeaking] = useState(false)
  const [provider, setProvider] = useState<TTSProvider>("web")
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const supported = typeof window !== "undefined" && "speechSynthesis" in window

  const stop = useCallback(() => {
    if (provider === "web") {
      if (typeof window !== "undefined" && (window as any).speechSynthesis) {
        (window as any).speechSynthesis.cancel()
      }
    } else {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
    }
    setSpeaking(false)
  }, [provider])

  const speakWeb = useCallback((text: string, lang: string = "de-DE") => {
    if (!supported || !text) return
    if ((window as any).speechSynthesis.speaking) {
      (window as any).speechSynthesis.cancel()
    }
    const u = new SpeechSynthesisUtterance(text)
    u.lang = lang
    u.rate = 1.0
    u.pitch = 1.0
    u.volume = 1.0
    u.onstart = () => setSpeaking(true)
    u.onend = () => setSpeaking(false)
    u.onerror = () => setSpeaking(false)
    utteranceRef.current = u
    ;(window as any).speechSynthesis.speak(u)
  }, [supported])

  const speakMiniMax = useCallback(async (text: string) => {
    if (!text.trim()) return
    setSpeaking(true)
    try {
      const res = await api.speakText(text.trim().slice(0, 3000), {
        language_boost: detectLanguage(text.trim()),
      })
      if (res.audio_url) {
        const audio = new Audio(res.audio_url)
        audioRef.current = audio
        audio.onended = () => { setSpeaking(false); audioRef.current = null }
        audio.onerror = () => { setSpeaking(false); audioRef.current = null }
        await audio.play()
      } else if (res.audio_hex) {
        const blob = hexToBlob(res.audio_hex, `audio/${res.audio_format || "mp3"}`)
        const url = URL.createObjectURL(blob)
        const audio = new Audio(url)
        audioRef.current = audio
        audio.onended = () => { setSpeaking(false); audioRef.current = null; URL.revokeObjectURL(url) }
        audio.onerror = () => { setSpeaking(false); audioRef.current = null; URL.revokeObjectURL(url) }
        await audio.play()
      } else {
        throw new Error("Keine Audio-Daten erhalten")
      }
    } catch (err: any) {
      console.error("MiniMax TTS-Fehler:", err)
      setSpeaking(false)
      throw err
    }
  }, [])

  const speak = useCallback((text: string, lang: string = "de-DE") => {
    stop()
    if (provider === "minimax") {
      speakMiniMax(text)
    } else {
      speakWeb(text, lang)
    }
  }, [provider, stop, speakWeb, speakMiniMax])

  return { speak, stop, speaking, supported, provider, setProvider }
}

// Einfache Spracherkennung fuer language_boost
function detectLanguage(text: string): string {
  if (/[\u4e00-\u9fff]/.test(text)) return "Chinese"
  if (/[\u3040-\u309f\u30a0-\u30ff]/.test(text)) return "Japanese"
  if (/[\uac00-\ud7af]/.test(text)) return "Korean"
  if (/[\u0600-\u06ff]/.test(text)) return "Arabic"
  if (/[\u0400-\u04ff]/.test(text)) return "Russian"
  if (/[äöüßÄÖÜ]|\b(der|die|das|und|ist|für|mit|von|den|dem|ein|eine)\b/i.test(text)) return "German"
  if (/[àâçéèêëîïôùûü]|\b(le|la|les|et|est|pour|avec|dans|une|un)\b/i.test(text)) return "French"
  if (/[áéíóúüñ¿¡]|\b(el|la|los|las|y|es|para|con|por|una|un)\b/i.test(text)) return "Spanish"
  if (/[áâãàçéêíóôõú]|\b(o|a|os|as|e|é|para|com|por|uma|um)\b/i.test(text)) return "Portuguese"
  if (/[àèéìòù]|\b(il|la|i|le|e|è|per|con|di|una|un)\b/i.test(text)) return "Italian"
  return "English"
}

function hexToBlob(hex: string, mimeType: string): Blob {
  const bytes = new Uint8Array(hex.length / 2)
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16)
  }
  return new Blob([bytes], { type: mimeType })
}
