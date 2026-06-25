# Voice-AI-Gateway — Konzept

> **Stand:** 25.06.2026
> **Status:** Konzept (zur User-Freigabe)
> **Hardware:** Quadro RTX 5000, 16 GB VRAM, ~448 GB/s Memory-Bandbreite (Turing sm_75)
> **Autor:** CIO-Assistant (basierend auf User-Direktive)

## 1. Ziel

Ein **lokaler, latenz-optimierter AI-Gateway-Server**, der von **allen Apps auf diesem Rechner** genutzt werden kann und folgende Services bietet:

1. **LLM-Inferenz** (Chat, Reasoning, Code) — OpenAI-kompatible API
2. **STT** (Speech-to-Text) — WebSocket + REST, Streaming-fähig, mit VAD
3. **TTS** (Text-to-Speech) — WebSocket + REST, Streaming, lokal
4. **Voice-Pipeline** (STT → LLM → TTS) — bidirektional, für Grill ME u.ä.

**Designziele:**
- **Latenz** < 1.5s pro Voice-Turn (Ziel: < 1s)
- **Multi-App** via einheitlicher HTTP/WS-API (kein App-spezifischer Code)
- **Multi-User** (mehrere Sessions parallel)
- **Lokal** (keine Cloud-Calls, Privacy garantiert)
- **Erweiterbar** (Modell-Swap, neue Tools ohne Architektur-Änderung)

## 2. Hardware-Constraints (Quadro RTX 5000)

| Spec | Wert | Implikation |
|------|------|-------------|
| VRAM | 16 GB GDDR6 | 14B-Modell @ Q8_0 = max, 14B @ Q4 = sweet spot |
| Compute Capability | 7.5 (Turing) | **Kein natives FP8** (erst Ada+) |
| Memory-Bandbreite | ~448 GB/s | Schneller als RTX 4060 Ti (288 GB/s), langsamer als RTX 4090 (1 TB/s) |
| CUDA Cores | 3072 | Vergleichbar mit RTX 2080 Super |
| Tensor Cores | 2. Gen (INT8/FP16) | AWQ INT4 ✓, FP8 ✗ |

**Konsequenzen:**
- **Quantisierung**: AWQ INT4 oder GGUF Q4_K_M bevorzugen (kein FP8)
- **Inferenz-Engine**: vLLM mit AWQ-Support ✓, SGLang ✓, llama.cpp ✓, TensorRT-LLM (FP8-Modus deaktiviert)
- **Speicher-Budget bei 16GB**: 14B-Modell (8-10GB) + STT (1-2GB) + TTS (1-2GB) + KV-Cache (2-3GB) = ~13-15GB → knapp aber machbar
- **Alternative Strategie**: Model-Swap bei Bedarf (Default-Modell + On-Demand)

## 3. Architektur

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Apps (Browser, Scripts, MCP-Clients)             │
│         grill_me.py  /  pi-desktop  /  scripts  /  other           │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ HTTP REST + WebSocket
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Voice-AI-Gateway  (FastAPI, Port 8000)                            │
│  ─────────────────────────────────────────────────                  │
│  • Unified API (OpenAI-compatible /chat/completions)               │
│  • WebSocket /voice (bidirektional: Audio rein, Audio raus)         │
│  • API-Key-Auth                                                     │
│  • Request-Routing → STT / LLM / TTS                              │
│  • Health & Metrics (Prometheus)                                   │
│  • Load-Balancing (bei mehreren Modellen)                         │
└──────┬──────────────┬──────────────┬──────────────┬────────────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ vLLM     │   │ STT      │   │ TTS      │   │ SGLang   │
│ Port 8001│   │ Port 8003│   │ Port 8004│   │ Port 8002│
│ (LLM)    │   │ (Whisper)│   │ (Kokoro/ │   │(structured│
│          │   │          │   │  Piper)  │   │ optional)│
└──────────┘   └──────────┘   └──────────┘   └──────────┘
       │              │              │              │
       └──────────────┴──────────────┴──────────────┘
                          │ alle teilen sich 16GB VRAM
                          ▼
                  ┌────────────────────┐
                  │ Quadro RTX 5000    │
                  │ 16 GB VRAM         │
                  └────────────────────┘
                          │
                  ┌────────────────────┐
                  │ WSSP-15 Heartbeat  │
                  │ Port 5680 (Discovery)│
                  └────────────────────┘
```

## 4. Komponenten-Entscheidungen (basierend auf Recherche 25.06.2026)

### 4.1 LLM-Server

**Empfehlung: vLLM als Default, SGLang optional für strukturierte Use-Cases**

Begründung:
- **vLLM** = beste TTFT, breite Modell-Unterstützung, OpenAI-kompatibel, einfach zu deployen
- **SGLang** = RadixAttention ideal für **Grill ME** (geteilter System-Prompt!), structured generation
- **llama.cpp** = Fallback für Edge/CPU-Modelle

**Modell-Empfehlung (16GB VRAM, Quadro RTX 5000):**

| Use-Case | Modell | Quant | VRAM | t/s (geschätzt) |
|----------|--------|-------|------|-----------------|
| **Default Chat** | Qwen3 14B | Q4_K_M | ~9 GB | ~30-35 |
| **Premium Quality** | Qwen3 14B | Q8_0 | ~14.8 GB | ~18-22 |
| **Coding** | Qwen3-Coder 14B | Q4_K_M | ~9 GB | ~30-35 |
| **Reasoning** | DeepSeek-R1 Distill 14B | Q4_K_M | ~9 GB | ~25-30 |
| **Speed/Multilingual** | Gemma 3 27B | Q4_K_M | ~15.8 GB (tight) | ~12-15 |
| **Fallback schnell** | Qwen2.5 7B | Q4_K_M | ~5 GB | ~50-60 |

**Default-Setup**: Qwen3 14B Q4_K_M (schnellste + beste Qualität/Balance)

### 4.2 STT (Speech-to-Text)

**Empfehlung: RealtimeSTT mit faster-whisper Backend**

| Option | Vorteil | Nachteil |
|--------|---------|----------|
| **RealtimeSTT** (KoljaB) | VAD + Wake-Word + Streaming, fertige FastAPI-Beispiel | Maintainer stepped back, "Community-Driven" |
| **faster-whisper** (allein) | Stabil, lokal, gut dokumentiert | Kein natives VAD/Streaming |
| **whisper-streaming** (ufoym) | Academic-grade Streaming | Komplexer zu integrieren |

**Empfehlung**: **RealtimeSTT** mit `faster-whisper` Engine, Silero VAD.
- Modell: `medium` (mehrsprachig, inkl. Deutsch, ~5GB VRAM)
- Wake-Word optional ("Hey Grill")
- Sprache: `de` (default), `en` (fallback)

### 4.3 TTS (Text-to-Speech)

**Empfehlung: Kokoro 82M als Default, Piper als Deutsch-Spezialist**

| Modell | First-Audio | Lizenz | Deutsch |
|--------|-------------|--------|---------|
| **Kokoro 82M** | 40ms | Apache 2.0 | ✗ |
| **Piper VITS** | 110ms | MIT/GPL-3 | ✓ (thorsten, eva, kerstin) |
| **Edge-TTS** | 500-1000ms | Cloud (proprietär) | ✓ (aktuelle Lösung) |

**Empfehlung**: 
- **Kokoro** als Default (schnellste, beste Qualität für nicht-Deutsch)
- **Piper** mit de-DE-Stimme als Deutsch-Default (latenz-kritisch, lokal)
- **Edge-TTS** als Cloud-Fallback falls lokales TTS ausfällt

### 4.4 Voice-Pipeline (STT → LLM → TTS)

**Latenz-Budget:**

| Phase | Optimal | Cloud-Aktuell | Lokal (unser Setup) |
|-------|---------|---------------|---------------------|
| STT (3s Audio) | 300-500ms | 1-3s (faster-whisper non-streaming) | 300-500ms (RealtimeSTT) |
| LLM (50 Tokens) | 500-1000ms | 1-2s (Ollama nicht-optimiert) | 500-800ms (vLLM) |
| TTS (20 Tokens) | 100-300ms | 1-2s (edge-tts cloud) | 100-200ms (Kokoro) |
| **Gesamt** | **<1s** | **3-6s** (zu lang!) | **<1.5s** ✓ |

## 5. Schnittstellen

### 5.1 LLM API (OpenAI-kompatibel)

```
POST http://127.0.0.1:8000/v1/chat/completions
Authorization: Bearer <API_KEY>
Content-Type: application/json

{
  "model": "qwen3-14b-q4",
  "messages": [{"role": "user", "content": "Hallo!"}],
  "stream": false,
  "temperature": 0.7
}
```

→ 100% kompatibel mit OpenAI-Client-Libraries (auch für Grill ME nutzbar).

### 5.2 STT API (REST + WebSocket)

**REST (File-Upload):**
```
POST http://127.0.0.1:8000/v1/audio/transcriptions
Content-Type: multipart/form-data
file: <audio.wav>
language: de
```

**WebSocket (Streaming):**
```
WS ws://127.0.0.1:8000/v1/audio/transcriptions/stream
→ Send: PCM-Audio-Chunks (16kHz, 16-bit, mono)
← Recv: {"text": "Hallo", "is_final": false, "confidence": 0.95}
```

### 5.3 TTS API (REST + WebSocket)

**REST:**
```
POST http://127.0.0.1:8000/v1/audio/speech
{
  "input": "Hallo Welt",
  "voice": "de-thorsten",
  "response_format": "mp3",
  "speed": 1.0
}
→ Audio-Bytes (mp3)
```

**WebSocket (Streaming):**
```
WS ws://127.0.0.1:8000/v1/audio/speech/stream
→ Send: {"text": "Hallo", "voice": "de-thorsten"}
← Recv: Audio-Chunks (Streaming)
```

### 5.4 Voice-Pipeline (bidirektional)

```
WS ws://127.0.0.1:8000/v1/voice
→ Send: PCM-Audio-Chunks (16kHz mono)
← Recv: 
   {"type": "stt_partial", "text": "Hal"}
   {"type": "stt_final", "text": "Hallo"}
   {"type": "llm_token", "text": "Hallo! "}
   {"type": "llm_token", "text": "Wie geht "}
   {"type": "tts_audio", "audio": <base64 mp3 chunk>}
   {"type": "done"}
```

**Ideal für Grill ME Voice-Mode.**

## 6. Port-Konzept (ME4-Konvention)

| Port | Service | Protokoll |
|------|---------|-----------|
| **8000** | Voice-AI-Gateway (unified API) | HTTP + WS |
| **8001** | vLLM (LLM primary) | HTTP (OpenAI-compatible) |
| **8002** | SGLang (LLM structured, optional) | HTTP |
| **8003** | STT Service (RealtimeSTT) | HTTP + WS |
| **8004** | TTS Service (Kokoro/Piper) | HTTP + WS |
| **5680** | WSSP-15 Heartbeat | WebSocket |

Gateway routet transparent, Apps sehen nur Port 8000.

## 7. VRAM-Management

Mit 16GB ist **nicht alles gleichzeitig** ladbar. Strategien:

**Strategie A: Sequenzielles Laden (einfach)**
- Default-Modell dauerhaft im VRAM (Qwen3 14B Q4 ~9GB)
- STT + TTS on-demand (laden wenn gebraucht, freigeben wenn idle)
- Voice-Pipeline: STT + LLM gleichzeitig (~14GB), TTS sequenziell

**Strategie B: Smart Loading (Production)**
- Watchdog-Prozess: LRU-Eviction
- Häufig genutzte Modelle dauerhaft
- Seltene on-demand mit Latenz-Hinweis

**Strategie C: Tier-System**
- Tier 1 (immer geladen): LLM-Default
- Tier 2 (on-demand): STT, TTS, alternative LLMs
- Tier 3 (Cold-Start): Spezial-Modelle

→ Wir starten mit **Strategie A** (einfach, deckt 90% der Use-Cases).

## 8. Implementation Plan (Phasen)

### Phase 1: Foundation (1-2 Tage)
- [ ] vLLM installieren + Qwen3 14B Q4_K_M laden
- [ ] Gateway-Service (FastAPI, Port 8000)
- [ ] OpenAI-kompatible `/v1/chat/completions` Route
- [ ] API-Key-Auth
- [ ] Smoke-Test

### Phase 2: STT (1-2 Tage)
- [ ] RealtimeSTT-Service (Port 8003)
- [ ] REST + WebSocket-Endpoints
- [ ] Integration in Gateway
- [ ] Smoke-Test mit deutschem Audio

### Phase 3: TTS (1-2 Tage)
- [ ] Kokoro + Piper lokal installieren
- [ ] TTS-Service (Port 8004)
- [ ] REST + WebSocket-Endpoints
- [ ] Streaming-Output
- [ ] Smoke-Test

### Phase 4: Voice-Pipeline (2-3 Tage)
- [ ] Voice-WebSocket-Endpoint im Gateway
- [ ] Orchestrierung: STT → LLM → TTS
- [ ] Latenz-Messung
- [ ] Grill-ME-Integration testen

### Phase 5: Polish (1-2 Tage)
- [ ] Metrics (Prometheus)
- [ ] Health-Checks
- [ ] Auto-Restart bei Crash
- [ ] Dokumentation
- [ ] Tests (E2E + Latenz-Benchmark)

**Gesamt-Aufwand: 6-10 Tage** (1 Entwickler Vollzeit)

## 9. Akzeptanzkriterien

1. **Latenz**: Voice-Turn < 1.5s (User-Wahrnehmung als „flüssig")
2. **Throughput**: Mindestens 3 parallele Sessions ohne Degradation
3. **API**: OpenAI-kompatibel (alle bestehenden Apps funktionieren ohne Änderung)
4. **Sprachen**: Deutsch + Englisch für STT und TTS
5. **Verfügbarkeit**: Auto-Restart, Health-Checks, Monitoring
6. **Doku**: API-Doc, Setup-Anleitung, Deployment-Guide
7. **Tests**: E2E-Test, Latenz-Benchmark, Multi-User-Stresstest

## 10. Risiken & Mitigationen

| Risiko | Impact | Mitigation |
|--------|--------|-----------|
| 16GB VRAM zu knapp für alle Services | Hoch | Strategie A: sequenzielles Laden |
| RealtimeSTT Maintainer inaktiv | Mittel | Fork-fähig, alternativ faster-whisper-only |
| Piper GPL-3 Lizenz | Niedrig | MIT-Alternativen (Kokoro für non-DE) |
| Kokoro kein Deutsch | Niedrig | Piper-Fallback für DE |
| Quadro RTX 5000 kein FP8 | Niedrig | AWQ INT4 verwenden |
| Model-Drift (neue Releases) | Niedrig | Modulares Modell-Slot-System |

## 11. Kosten & Lizenz-Übersicht

| Komponente | Lizenz | Kosten |
|-----------|--------|--------|
| vLLM | Apache 2.0 | $0 |
| SGLang | Apache 2.0 | $0 |
| RealtimeSTT | MIT | $0 |
| Kokoro 82M | Apache 2.0 | $0 |
| Piper | MIT (rhasspy/piper archiviert) | $0 |
| Faster-Whisper | MIT | $0 |
| Qwen3 14B | Apache 2.0 | $0 |
| **Total** | **100% OSS** | **$0** |

## 12. Nächste Schritte

1. **User-Freigabe** für dieses Konzept
2. **Reihenfolge** festlegen (alle Phasen? Nur Phase 1?)
3. **Phase 1 umsetzen**: vLLM + Qwen3 14B + minimaler Gateway
4. Smoke-Test mit echtem Use-Case (z.B. Grill ME)
5. Bei Erfolg: Phase 2-5

## 13. Recherche-Quellen

- https://llmhardware.io/guides/best-llm-for-16gb-vram
- https://willitrunai.com/blog/what-can-you-run-on-16gb-24gb-32gb-vram
- https://craftrigs.com/tools/best-local-llm-models-ranked/
- https://github.com/KoljaB/RealtimeSTT
- https://huggingface.co/hexgrad/Kokoro-82M
- https://github.com/rhasspy/piper
- https://gigagpu.com/tts-latency-benchmarks/
- https://jarvislabs.ai/blog/vllm-sglang-trtllm-comparison
- https://www.f22labs.com/blogs/trt-llm-vs-vllm-vs-sglang-what-to-choose-in-2026-2/