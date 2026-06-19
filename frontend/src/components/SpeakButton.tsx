import { useState, useCallback, useRef, useEffect } from "react"
import { useTTSContext } from "../TTSContext"
import { Volume2, VolumeX } from "lucide-react"

interface SpeakButtonProps {
  text: string
  label?: string
  size?: number
  className?: string
  showLabel?: boolean
}

/**
 * Wiederverwendbarer Vorlese-Button.
 * Nutzt den globalen TTSContext. Im TTS-Modus "click" wird der Text vorgelesen.
 * Bei aktivem Speaking faerbt sich der Button orange (klick zum Stoppen).
 */
export function SpeakButton({ text, label, size = 12, className = "", showLabel = false }: SpeakButtonProps) {
  const tts = useTTSContext()
  const [lastText, setLastText] = useState("")
  const isSpeakingThis = tts.speaking && lastText === text

  function handleClick(e: React.MouseEvent) {
    e.stopPropagation()
    e.preventDefault()
    if (tts.speaking) {
      tts.stop()
    } else {
      setLastText(text)
      tts.speakText(text)
    }
  }

  if (tts.mode === "off") return null

  return (
    <button
      className={`btn btn-sm ${className}`}
      onClick={handleClick}
      title={tts.speaking && isSpeakingThis ? "Vorlesen stoppen" : "Vorlesen"}
      style={{
        padding: "2px 6px",
        fontSize: 10,
        background: tts.speaking && isSpeakingThis ? "rgba(210, 153, 34, 0.2)" : "transparent",
        color: tts.speaking && isSpeakingThis ? "var(--color-hermes-accent-orange)" : "var(--color-hermes-text-secondary)",
        border: "1px solid var(--color-hermes-border)",
      }}
    >
      {tts.speaking && isSpeakingThis ? <VolumeX size={size} /> : <Volume2 size={size} />}
      {showLabel && <span style={{ marginLeft: 4 }}>{label || "Vorlesen"}</span>}
    </button>
  )
}
