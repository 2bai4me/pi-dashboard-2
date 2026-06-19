// AgentQuestions.tsx — User <-> Agent Interaktionstool
//
// User-Direktive 17.06.2026:
//   Agenten jeder Ebene (C-Level, Worker, Subagent) koennen Fragen an
//   den User stellen. Der User beantwortet sie mit Text, Dateien oder
//   Bildern. Live-Polling holt neue Fragen alle 5s.
//
// Sub-Tab "Live-Operator": zeigt alle aktiven Board-Operatoren (Watchdog).

import { useEffect, useState, useRef, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../api"
import { UserInputForm } from "../components/UserInputForm"
import {
  AlertCircle,
  AlertTriangle,
  Archive,
  ArrowLeft,
  Bell,
  BellOff,
  CheckCircle2,
  CheckSquare,
  Circle,
  Clock,
  Download,
  FileText,
  Image as ImageIcon,
  Inbox,
  Loader2,
  MessageSquare,
  Paperclip,
  Radio,
  RefreshCw,
  Send,
  Square,
  Trash2,
  Upload,
  User as UserIcon,
  Wrench,
  X,
  XCircle,
  Zap,
} from "lucide-react"

type SubTab = "questions" | "operators"
type FilterStatus = "open" | "pending" | "answered" | "cancelled" | "expired" | "all"

// =====================================================
//  Hauptkomponente
// =====================================================
export default function AgentQuestions() {
  const [subTab, setSubTab] = useState<SubTab>("questions")
  const [filter, setFilter] = useState<FilterStatus>("open")
  const [selectedId, setSelectedId] = useState<string | null>(null)

  return (
    <div>
      <div className="page-header">
        <h1>
          <Wrench size={20} style={{ marginRight: 8, verticalAlign: "text-bottom" }} />
          Tools
        </h1>
        <p>Interaktion zwischen User und Agent &middot; Live-Operatoren</p>
      </div>

      {/* Sub-Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, borderBottom: "1px solid var(--color-hermes-border, #333)", paddingBottom: 0 }}>
        <SubTabButton current={subTab} value="questions" onClick={() => setSubTab("questions")}>
          <MessageSquare size={14} style={{ marginRight: 6, verticalAlign: "text-bottom" }} />
          User Input
        </SubTabButton>
        <SubTabButton current={subTab} value="operators" onClick={() => setSubTab("operators")}>
          <Radio size={14} style={{ marginRight: 6, verticalAlign: "text-bottom" }} />
          Live-Operatoren
        </SubTabButton>
      </div>

      {subTab === "questions" ? (
        <QuestionsView filter={filter} setFilter={setFilter} selectedId={selectedId} setSelectedId={setSelectedId} />
      ) : (
        <OperatorsView />
      )}
    </div>
  )
}

// =====================================================
//  Sub-Tab Button
// =====================================================
function SubTabButton({ current, value, onClick, children }: {
  current: SubTab
  value: SubTab
  onClick: () => void
  children: React.ReactNode
}) {
  const active = current === value
  return (
    <button
      onClick={onClick}
      style={{
        background: "transparent",
        border: "none",
        color: active ? "var(--color-hermes-accent, #7c3aed)" : "var(--color-hermes-text-secondary, #999)",
        padding: "10px 16px",
        cursor: "pointer",
        borderBottom: active ? "2px solid var(--color-hermes-accent, #7c3aed)" : "2px solid transparent",
        fontSize: 14,
        fontWeight: active ? 600 : 400,
      }}
    >
      {children}
    </button>
  )
}

// =====================================================
//  Questions View (Hauptansicht)
// =====================================================
function QuestionsView({ filter, setFilter, selectedId, setSelectedId }: {
  filter: FilterStatus
  setFilter: (f: FilterStatus) => void
  selectedId: string | null
  setSelectedId: (id: string | null) => void
}) {
  const queryClient = useQueryClient()

  // Liste laden (mit Polling alle 5s)
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["agent-questions", filter],
    queryFn: () => {
      const status = filter === "open" ? "open" : filter === "all" ? undefined : filter
      return api.agentQuestions.list({ status, limit: 100 })
    },
    refetchInterval: 30000,
  })

  // Pending count
  const { data: pendingData } = useQuery({
    queryKey: ["agent-questions-pending"],
    queryFn: () => api.agentQuestions.pendingCount(),
    refetchInterval: 30000,
  })

  const items = (data?.items || []) as any[]
  const pending = pendingData?.pending ?? 0
  const unseen = pendingData?.unseen ?? 0

  // Wenn eine Frage markiert wird, sofort als "seen" markieren
  useEffect(() => {
    if (selectedId) {
      api.agentQuestions.markSeen(selectedId).then(() => {
        queryClient.invalidateQueries({ queryKey: ["agent-questions-pending"] })
      }).catch(() => {})
    }
  }, [selectedId, queryClient])

  return (
    <div style={{ display: "grid", gridTemplateColumns: selectedId ? "380px 1fr" : "1fr", gap: 16 }}>
      {/* Linke Spalte: Liste + Filter */}
      <div>
        {/* Filter */}
        <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
          <FilterChip current={filter} value="open" onClick={() => setFilter("open")} icon={<Inbox size={12} />} count={pending} />
          <FilterChip current={filter} value="pending" onClick={() => setFilter("pending")} />
          <FilterChip current={filter} value="answered" onClick={() => setFilter("answered")} icon={<CheckCircle2 size={12} />} />
          <FilterChip current={filter} value="cancelled" onClick={() => setFilter("cancelled")} icon={<XCircle size={12} />} />
          <FilterChip current={filter} value="all" onClick={() => setFilter("all")} />
        </div>

        {unseen > 0 && filter === "open" && (
          <div
            style={{
              background: "rgba(245, 158, 11, 0.1)",
              border: "1px solid rgba(245, 158, 11, 0.3)",
              borderRadius: 6,
              padding: "8px 12px",
              marginBottom: 12,
              fontSize: 12,
              color: "#f59e0b",
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <Bell size={14} /> {unseen} ungesehene {unseen === 1 ? "Frage" : "Fragen"}
          </div>
        )}

        {/* Liste */}
        {isLoading ? (
          <LoadingBox />
        ) : items.length === 0 ? (
          <EmptyBox filter={filter} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {items.map((q) => (
              <QuestionListItem
                key={q.id}
                question={q}
                selected={selectedId === q.id}
                onClick={() => setSelectedId(q.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Rechte Spalte: Detail */}
      {selectedId && (
        <QuestionDetail
          questionId={selectedId}
          onClose={() => setSelectedId(null)}
          onAnswered={() => {
            setSelectedId(null)
            queryClient.invalidateQueries({ queryKey: ["agent-questions"] })
            queryClient.invalidateQueries({ queryKey: ["agent-questions-pending"] })
          }}
          onCancelled={() => {
            setSelectedId(null)
            queryClient.invalidateQueries({ queryKey: ["agent-questions"] })
          }}
        />
      )}
    </div>
  )
}

// =====================================================
//  Filter Chip
// =====================================================
function FilterChip({ current, value, onClick, icon, count }: {
  current: FilterStatus
  value: FilterStatus
  onClick: () => void
  icon?: React.ReactNode
  count?: number
}) {
  const active = current === value
  return (
    <button
      onClick={onClick}
      style={{
        background: active ? "var(--color-hermes-accent, #7c3aed)" : "transparent",
        color: active ? "#fff" : "var(--color-hermes-text-secondary, #999)",
        border: `1px solid ${active ? "var(--color-hermes-accent, #7c3aed)" : "var(--color-hermes-border, #333)"}`,
        borderRadius: 16,
        padding: "4px 10px",
        fontSize: 12,
        cursor: "pointer",
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
      }}
    >
      {icon}
      {value === "open" ? "Offen" : value === "pending" ? "Pending" : value === "answered" ? "Beantwortet" : value === "cancelled" ? "Storniert" : "Alle"}
      {count !== undefined && count > 0 && (
        <span
          style={{
            background: active ? "rgba(255,255,255,0.2)" : "rgba(124, 58, 237, 0.2)",
            borderRadius: 10,
            padding: "0 6px",
            fontSize: 11,
            marginLeft: 2,
          }}
        >
          {count}
        </span>
      )}
    </button>
  )
}

// =====================================================
//  List Item
// =====================================================
function QuestionListItem({ question, selected, onClick }: {
  question: any
  selected: boolean
  onClick: () => void
}) {
  const age = formatAge(question.created_at)
  const priorityColor = {
    urgent: "#dc2626",
    high: "#f59e0b",
    medium: "#3b82f6",
    low: "#6b7280",
  }[question.priority] || "#6b7280"
  const isUnseen = !question.seen_at && question.status === "pending"

  return (
    <div
      onClick={onClick}
      style={{
        background: selected ? "rgba(124, 58, 237, 0.15)" : "var(--color-hermes-bg-card, #1a1a1a)",
        border: `1px solid ${selected ? "var(--color-hermes-accent, #7c3aed)" : "var(--color-hermes-border, #333)"}`,
        borderLeft: `3px solid ${priorityColor}`,
        borderRadius: 6,
        padding: "10px 12px",
        cursor: "pointer",
        position: "relative",
        transition: "all 0.1s",
      }}
    >
      {isUnseen && (
        <div
          style={{
            position: "absolute",
            top: 8,
            right: 8,
            width: 8,
            height: 8,
            background: "#f59e0b",
            borderRadius: "50%",
          }}
        />
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4, fontSize: 11, color: "var(--color-hermes-text-secondary, #999)" }}>
        <AgentLevelBadge level={question.agent_level} />
        <span style={{ flex: 1 }} />
        <Clock size={10} />
        <span>{age}</span>
      </div>
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
        {question.title}
      </div>
      <div style={{ fontSize: 12, color: "var(--color-hermes-text-secondary, #999)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {question.question}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, fontSize: 11 }}>
        <TypeBadge type={question.question_type} />
        {question.attachment_count > 0 && (
          <span style={{ color: "var(--color-hermes-text-secondary, #999)", display: "flex", alignItems: "center", gap: 2 }}>
            <Paperclip size={10} /> {question.attachment_count}
          </span>
        )}
        {question.status === "answered" && (
          <span style={{ color: "#10b981", display: "flex", alignItems: "center", gap: 2 }}>
            <CheckCircle2 size={10} /> beantwortet
          </span>
        )}
        {question.status === "cancelled" && (
          <span style={{ color: "#6b7280", display: "flex", alignItems: "center", gap: 2 }}>
            <XCircle size={10} /> storniert
          </span>
        )}
      </div>
    </div>
  )
}

// =====================================================
//  Detail View
// =====================================================
function QuestionDetail({ questionId, onClose, onAnswered, onCancelled }: {
  questionId: string
  onClose: () => void
  onAnswered: () => void
  onCancelled: () => void
}) {
  const queryClient = useQueryClient()
  const { data: question, isLoading } = useQuery({
    queryKey: ["agent-question", questionId],
    queryFn: () => api.agentQuestions.get(questionId),
    refetchInterval: 30000,
  })

  const answerMut = useMutation({
    mutationFn: (data: { answer_text?: string; answer_choice?: string }) =>
      api.agentQuestions.answer(questionId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent-question", questionId] })
      onAnswered()
    },
  })

  const cancelMut = useMutation({
    mutationFn: () => api.agentQuestions.cancel(questionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent-question", questionId] })
      onCancelled()
    },
  })

  if (isLoading || !question) return <LoadingBox />

  return (
    <div
      style={{
        background: "var(--color-hermes-bg-card, #1a1a1a)",
        border: "1px solid var(--color-hermes-border, #333)",
        borderRadius: 8,
        padding: 20,
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 16 }}>
        <button
          onClick={onClose}
          style={{ background: "transparent", border: "none", color: "#999", cursor: "pointer", padding: 4 }}
          title="Zurück"
        >
          <ArrowLeft size={18} />
        </button>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, flexWrap: "wrap" }}>
            <AgentLevelBadge level={question.agent_level} />
            <span style={{ fontSize: 12, color: "#999" }}>
              {question.agent_label || question.agent_id}
            </span>
            <PriorityBadge priority={question.priority} />
            <TypeBadge type={question.question_type} />
            <span style={{ fontSize: 11, color: "#999" }}>· {formatAge(question.created_at)}</span>
          </div>
          <h2 style={{ margin: "0 0 8px 0", fontSize: 18 }}>{question.title}</h2>
        </div>
        {question.status === "pending" && (
          <button
            onClick={() => {
              if (confirm("Diese Frage stornieren?")) cancelMut.mutate()
            }}
            disabled={cancelMut.isPending}
            style={{
              background: "transparent",
              border: "1px solid #6b7280",
              color: "#6b7280",
              borderRadius: 6,
              padding: "6px 10px",
              fontSize: 12,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <Trash2 size={12} /> Stornieren
          </button>
        )}
      </div>

      {/* Frage-Text */}
      <div
        style={{
          background: "rgba(255, 255, 255, 0.03)",
          border: "1px solid var(--color-hermes-border, #333)",
          borderLeft: "3px solid #3b82f6",
          borderRadius: 6,
          padding: 14,
          marginBottom: 16,
          fontSize: 14,
          lineHeight: 1.5,
          whiteSpace: "pre-wrap",
        }}
      >
        {question.question}
      </div>

      {/* Agent-Attachments (falls vorhanden) */}
      {question.attachments && question.attachments.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: "#999", marginBottom: 6 }}>
            Anhaenge des Agenten:
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {question.attachments
              .filter((a: any) => a.source === "agent")
              .map((a: any) => (
                <AttachmentPreview key={a.id} questionId={questionId} att={a} />
              ))}
          </div>
        </div>
      )}

      {/* Kontext (falls vorhanden) */}
      {question.context && Object.keys(question.context).length > 0 && (
        <details style={{ marginBottom: 16, fontSize: 12 }}>
          <summary style={{ cursor: "pointer", color: "#999" }}>Kontext anzeigen</summary>
          <pre
            style={{
              background: "rgba(0,0,0,0.3)",
              padding: 8,
              borderRadius: 4,
              fontSize: 11,
              overflow: "auto",
              marginTop: 6,
            }}
          >
            {JSON.stringify(question.context, null, 2)}
          </pre>
        </details>
      )}

      {/* Antwort-Form (nur bei pending) */}
      {question.status === "pending" ? (
        <UserInputForm
          question={question}
          onSubmit={async (text) => {
            answerMut.mutate({ answer_text: text })
          }}
          isSubmitting={answerMut.isPending}
        />
      ) : (
        <AnswerDisplay question={question} />
      )}
    </div>
  )
}

// =====================================================
//  Answer Form (je nach question_type)
// =====================================================
function AnswerForm({ question, onSubmit, isSubmitting }: {
  question: any
  onSubmit: (data: { answer_text?: string; answer_choice?: string }) => void
  isSubmitting: boolean
}) {
  const [text, setText] = useState("")
  const [attachments, setAttachments] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  // Upload-Handler
  const handleFileSelect = (files: FileList | null) => {
    if (!files) return
    setAttachments((prev) => [...prev, ...Array.from(files)])
  }

  const uploadAllAttachments = async (questionId: string) => {
    for (const file of attachments) {
      const kind = file.type.startsWith("image/") ? "image" : "file"
      try {
        await api.agentQuestions.uploadAttachment(questionId, file, "user", kind)
      } catch (e) {
        console.error("Upload fehlgeschlagen:", file.name, e)
      }
    }
  }

  const handleSubmit = async () => {
    if (question.question_type === "confirmation") {
      if (text.toLowerCase() !== "ja" && text.toLowerCase() !== "nein") {
        alert("Bei Bestaetigungs-Fragen bitte 'ja' oder 'nein' eingeben")
        return
      }
    }
    if (question.question_type === "choice" && !text) {
      alert("Bitte eine Option waehlen")
      return
    }
    if (question.question_type !== "choice" && !text.trim()) {
      alert("Bitte eine Antwort eingeben")
      return
    }

    // Bei choice: text -> answer_choice mappen
    const answer_choice = question.question_type === "choice" ? text : undefined
    const answer_text = question.question_type !== "choice" ? text : undefined

    onSubmit({ answer_text, answer_choice })
    // Attachments werden nach dem Answer hochgeladen
    if (attachments.length > 0) {
      // Erst hochladen, dann Query invalidieren
      await uploadAllAttachments(question.id)
      queryClient.invalidateQueries({ queryKey: ["agent-question", question.id] })
    }
  }

  // === Choice-Frage: Buttons statt Textfeld
  if (question.question_type === "choice" && question.options?.length > 0) {
    return (
      <div>
        <div style={{ fontSize: 12, color: "#999", marginBottom: 8 }}>Bitte eine Option waehlen:</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 16 }}>
          {question.options.map((opt: string) => (
            <button
              key={opt}
              onClick={() => onSubmit({ answer_choice: opt })}
              disabled={isSubmitting}
              style={{
                background: text === opt ? "var(--color-hermes-accent, #7c3aed)" : "transparent",
                border: `1px solid ${text === opt ? "var(--color-hermes-accent, #7c3aed)" : "var(--color-hermes-border, #333)"}`,
                color: text === opt ? "#fff" : "var(--color-hermes-text, #e5e5e5)",
                borderRadius: 6,
                padding: "10px 14px",
                fontSize: 14,
                cursor: "pointer",
                textAlign: "left",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              {text === opt ? <CheckSquare size={16} /> : <Square size={16} />}
              {opt}
            </button>
          ))}
        </div>
        {isSubmitting && <div style={{ fontSize: 12, color: "#999" }}>Wird gesendet...</div>}
      </div>
    )
  }

  // === Confirmation: Quick-Buttons
  if (question.question_type === "confirmation") {
    return (
      <div>
        <AttachmentList attachments={attachments} onRemove={(i) => setAttachments(attachments.filter((_, idx) => idx !== i))} />
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button
            onClick={() => onSubmit({ answer_text: "ja" })}
            disabled={isSubmitting}
            style={{
              background: "rgba(16, 185, 129, 0.15)",
              border: "1px solid #10b981",
              color: "#10b981",
              borderRadius: 6,
              padding: "10px 20px",
              fontSize: 14,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <CheckCircle2 size={16} /> Ja
          </button>
          <button
            onClick={() => onSubmit({ answer_text: "nein" })}
            disabled={isSubmitting}
            style={{
              background: "rgba(220, 38, 38, 0.15)",
              border: "1px solid #dc2626",
              color: "#dc2626",
              borderRadius: 6,
              padding: "10px 20px",
              fontSize: 14,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <XCircle size={16} /> Nein
          </button>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Optional: Begruendung oder Kommentar..."
          rows={2}
          style={{
            width: "100%",
            background: "rgba(0,0,0,0.3)",
            border: "1px solid var(--color-hermes-border, #333)",
            borderRadius: 6,
            padding: 10,
            color: "var(--color-hermes-text, #e5e5e5)",
            fontSize: 13,
            marginBottom: 8,
            boxSizing: "border-box",
          }}
        />
        <FileUploadRow onSelect={handleFileSelect} fileInputRef={fileInputRef} count={attachments.length} />
        <SubmitRow onSubmit={handleSubmit} isSubmitting={isSubmitting} text="Antwort senden" />
      </div>
    )
  }

  // === Text/Image/Attachment/Any: Textarea + Uploads
  return (
    <div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Deine Antwort..."
        rows={5}
        autoFocus
        style={{
          width: "100%",
          background: "rgba(0,0,0,0.3)",
          border: "1px solid var(--color-hermes-border, #333)",
          borderRadius: 6,
          padding: 10,
          color: "var(--color-hermes-text, #e5e5e5)",
          fontSize: 14,
          marginBottom: 8,
          boxSizing: "border-box",
          resize: "vertical",
          fontFamily: "inherit",
        }}
      />

      <AttachmentList attachments={attachments} onRemove={(i) => setAttachments(attachments.filter((_, idx) => idx !== i))} />

      <FileUploadRow onSelect={handleFileSelect} fileInputRef={fileInputRef} count={attachments.length} />
      <SubmitRow onSubmit={handleSubmit} isSubmitting={isSubmitting} />
    </div>
  )
}

// =====================================================
//  Drag & Drop File Upload
// =====================================================
function FileUploadRow({ onSelect, fileInputRef, count }: {
  onSelect: (files: FileList | null) => void
  fileInputRef: React.RefObject<HTMLInputElement | null>
  count: number
}) {
  const [dragOver, setDragOver] = useState(false)

  return (
    <div style={{ marginBottom: 12 }}>
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragOver(false)
          onSelect(e.dataTransfer.files)
        }}
        onClick={() => fileInputRef.current?.click()}
        style={{
          border: `2px dashed ${dragOver ? "var(--color-hermes-accent, #7c3aed)" : "var(--color-hermes-border, #333)"}`,
          borderRadius: 6,
          padding: "12px 16px",
          textAlign: "center",
          cursor: "pointer",
          fontSize: 12,
          color: dragOver ? "var(--color-hermes-accent, #7c3aed)" : "var(--color-hermes-text-secondary, #999)",
          background: dragOver ? "rgba(124, 58, 237, 0.05)" : "transparent",
          transition: "all 0.1s",
        }}
      >
        <Upload size={16} style={{ marginRight: 6, verticalAlign: "text-bottom" }} />
        Datei hier ablegen oder klicken zum Auswaehlen
        {count > 0 && (
          <span style={{ marginLeft: 8, color: "var(--color-hermes-accent, #7c3aed)", fontWeight: 600 }}>
            ({count} ausgewaehlt)
          </span>
        )}
      </div>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        style={{ display: "none" }}
        onChange={(e) => onSelect(e.target.files)}
      />
    </div>
  )
}

function AttachmentList({ attachments, onRemove }: {
  attachments: File[]
  onRemove: (i: number) => void
}) {
  if (attachments.length === 0) return null
  return (
    <div style={{ marginBottom: 8, display: "flex", flexDirection: "column", gap: 4 }}>
      {attachments.map((f, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            background: "rgba(0,0,0,0.3)",
            border: "1px solid var(--color-hermes-border, #333)",
            borderRadius: 4,
            padding: "6px 10px",
            fontSize: 12,
          }}
        >
          {f.type.startsWith("image/") ? <ImageIcon size={14} /> : <FileText size={14} />}
          <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</span>
          <span style={{ color: "#999", fontSize: 11 }}>{formatBytes(f.size)}</span>
          <button
            onClick={() => onRemove(i)}
            style={{ background: "transparent", border: "none", color: "#dc2626", cursor: "pointer", padding: 0 }}
            title="Entfernen"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}

function SubmitRow({ onSubmit, isSubmitting, text = "Senden" }: {
  onSubmit: () => void
  isSubmitting: boolean
  text?: string
}) {
  return (
    <button
      onClick={onSubmit}
      disabled={isSubmitting}
      style={{
        background: "var(--color-hermes-accent, #7c3aed)",
        color: "#fff",
        border: "none",
        borderRadius: 6,
        padding: "10px 16px",
        fontSize: 14,
        fontWeight: 600,
        cursor: isSubmitting ? "wait" : "pointer",
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        opacity: isSubmitting ? 0.7 : 1,
      }}
    >
      {isSubmitting ? <Loader2 size={14} className="spin" /> : <Send size={14} />}
      {text}
    </button>
  )
}

// =====================================================
//  Answer Display (fuer beantwortete Fragen)
// =====================================================
function AnswerDisplay({ question }: { question: any }) {
  return (
    <div
      style={{
        background: "rgba(16, 185, 129, 0.08)",
        border: "1px solid rgba(16, 185, 129, 0.3)",
        borderLeft: "3px solid #10b981",
        borderRadius: 6,
        padding: 14,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, fontSize: 12, color: "#10b981" }}>
        <CheckCircle2 size={14} />
        <strong>Beantwortet</strong>
        {question.answered_by && <span style={{ color: "#999" }}>· von {question.answered_by}</span>}
        {question.answered_at && <span style={{ color: "#999" }}>· {formatAge(question.answered_at)}</span>}
      </div>
      {question.answer_choice && (
        <div style={{ fontSize: 14, marginBottom: 6 }}>
          <strong>Gewaehlte Option:</strong> {question.answer_choice}
        </div>
      )}
      {question.answer_text && (
        <div style={{ fontSize: 14, whiteSpace: "pre-wrap" }}>{question.answer_text}</div>
      )}
      {/* User-Anhaenge anzeigen */}
      {question.attachments && question.attachments.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, color: "#999", marginBottom: 6 }}>Anhaenge des Users:</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {question.attachments
              .filter((a: any) => a.source === "user")
              .map((a: any) => (
                <AttachmentPreview key={a.id} questionId={question.id} att={a} />
              ))}
          </div>
        </div>
      )}
    </div>
  )
}

// =====================================================
//  Attachment Preview (Bild oder File)
// =====================================================
function AttachmentPreview({ questionId, att }: { questionId: string; att: any }) {
  const url = api.agentQuestions.attachmentUrl(questionId, att.id)
  if (att.kind === "image" || att.mime_type?.startsWith("image/")) {
    return (
      <a href={url} target="_blank" rel="noreferrer" style={{ display: "block" }}>
        <img
          src={url}
          alt={att.file_name}
          style={{
            maxWidth: 180,
            maxHeight: 180,
            borderRadius: 6,
            border: "1px solid var(--color-hermes-border, #333)",
            objectFit: "cover",
          }}
        />
      </a>
    )
  }
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        background: "rgba(0,0,0,0.3)",
        border: "1px solid var(--color-hermes-border, #333)",
        borderRadius: 4,
        padding: "6px 10px",
        fontSize: 12,
        color: "var(--color-hermes-text, #e5e5e5)",
        textDecoration: "none",
      }}
    >
      <FileText size={14} />
      {att.file_name}
      <Download size={12} style={{ marginLeft: 4, opacity: 0.6 }} />
    </a>
  )
}

// =====================================================
//  Operators View
// =====================================================
function OperatorsView() {
  const queryClient = useQueryClient()
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["operators"],
    queryFn: () => api.operators.list(),
    refetchInterval: 30000,
  })

  const items = (data?.items || []) as any[]

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <h3 style={{ margin: 0 }}>Aktive Watchdog-Operatoren</h3>
        <span style={{ fontSize: 12, color: "#999" }}>({items.length})</span>
        <button
          onClick={() => refetch()}
          style={{ background: "transparent", border: "1px solid #444", color: "#999", borderRadius: 4, padding: "4px 8px", fontSize: 12, cursor: "pointer", marginLeft: "auto", display: "flex", alignItems: "center", gap: 4 }}
        >
          <RefreshCw size={12} /> Aktualisieren
        </button>
      </div>

      <p style={{ fontSize: 12, color: "#999", marginBottom: 16 }}>
        Jedes Board mit <code>mode=live</code> hat eine eigenstaendige Operator-Instanz, die
        alle 5s einen Heartbeat sendet. Nur bei aktivem Heartbeat leuchtet das Live-Icon gruen.
        Der Operator prueft zudem alle 30s die Tasks des Boards auf haengende States.
      </p>

      {isLoading ? (
        <LoadingBox />
      ) : items.length === 0 ? (
        <EmptyBox
          filter="operators"
          message="Keine Board-Operatoren. Setze ein Board auf mode=live, um einen Operator zu starten."
        />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: 12 }}>
          {items.map((op) => (
            <OperatorCard key={op.id} op={op} onChange={() => queryClient.invalidateQueries({ queryKey: ["operators"] })} />
          ))}
        </div>
      )}
    </div>
  )
}

function OperatorCard({ op, onChange }: { op: any; onChange: () => void }) {
  const stopMut = useMutation({
    mutationFn: () => api.operators.stop(op.board_id, "user_request"),
    onSuccess: onChange,
  })

  const startMut = useMutation({
    mutationFn: () => api.operators.start(op.board_id),
    onSuccess: onChange,
  })

  return (
    <div
      style={{
        background: "var(--color-hermes-bg-card, #1a1a1a)",
        border: "1px solid var(--color-hermes-border, #333)",
        borderLeft: `3px solid ${liveColor(op.live_color)}`,
        borderRadius: 6,
        padding: 14,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <LiveDot color={op.live_color} />
        <strong style={{ fontSize: 14 }}>Board {op.board_id.slice(0, 8)}</strong>
        <span style={{ fontSize: 11, color: "#999" }}>· {op.live_label}</span>
        <span style={{ marginLeft: "auto" }}>
          {op.agent_status === "stopped" || op.agent_status === "error" || op.agent_status === "not_started" ? (
            <button
              onClick={() => startMut.mutate()}
              disabled={startMut.isPending}
              style={{ background: "#10b981", color: "#fff", border: "none", borderRadius: 4, padding: "4px 10px", fontSize: 11, cursor: "pointer" }}
            >
              Start
            </button>
          ) : (
            <button
              onClick={() => stopMut.mutate()}
              disabled={stopMut.isPending}
              style={{ background: "#6b7280", color: "#fff", border: "none", borderRadius: 4, padding: "4px 10px", fontSize: 11, cursor: "pointer" }}
            >
              Stop
            </button>
          )}
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 12, color: "#bbb" }}>
        <div>Heartbeat: <span style={{ color: "var(--color-hermes-text, #e5e5e5)" }}>{op.last_heartbeat_age_s !== null ? `${op.last_heartbeat_age_s}s alt` : "—"}</span></div>
        <div>Status: <span style={{ color: liveColor(op.live_color) }}>{op.agent_status}</span></div>
        <div>Checks: <span style={{ color: "var(--color-hermes-text, #e5e5e5)" }}>{op.checks_total}</span></div>
        <div>Stale gefunden: <span style={{ color: "var(--color-hermes-text, #e5e5e5)" }}>{op.stale_tasks_found}</span></div>
        <div>Alerts: <span style={{ color: "var(--color-hermes-text, #e5e5e5)" }}>{op.alerts_sent}</span></div>
        <div>Fragen: <span style={{ color: "var(--color-hermes-text, #e5e5e5)" }}>{op.questions_asked}</span></div>
      </div>

      {op.error_message && (
        <div style={{ marginTop: 8, padding: 6, background: "rgba(220, 38, 38, 0.1)", border: "1px solid #dc2626", borderRadius: 4, fontSize: 11, color: "#dc2626" }}>
          {op.error_message}
        </div>
      )}
    </div>
  )
}

function LiveDot({ color }: { color: string }) {
  const c = liveColor(color)
  return (
    <div
      style={{
        width: 10,
        height: 10,
        borderRadius: "50%",
        background: c,
        boxShadow: color === "green" ? `0 0 8px ${c}` : "none",
      }}
    />
  )
}

function liveColor(name: string): string {
  return {
    green: "#10b981",
    yellow: "#f59e0b",
    red: "#dc2626",
    gray: "#6b7280",
  }[name] || "#6b7280"
}

// =====================================================
//  Badges
// =====================================================
function AgentLevelBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    "C-Level": "#a855f7",
    "Worker": "#3b82f6",
    "Subagent": "#06b6d4",
  }
  const c = colors[level] || "#6b7280"
  return (
    <span
      style={{
        background: c,
        color: "#fff",
        padding: "1px 6px",
        borderRadius: 3,
        fontSize: 10,
        fontWeight: 600,
      }}
    >
      {level}
    </span>
  )
}

function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    urgent: "#dc2626",
    high: "#f59e0b",
    medium: "#3b82f6",
    low: "#6b7280",
  }
  const c = colors[priority] || "#6b7280"
  return (
    <span
      style={{
        background: "transparent",
        border: `1px solid ${c}`,
        color: c,
        padding: "0 6px",
        borderRadius: 3,
        fontSize: 10,
        fontWeight: 600,
        textTransform: "uppercase",
      }}
    >
      {priority}
    </span>
  )
}

function TypeBadge({ type }: { type: string }) {
  const icons: Record<string, React.ReactNode> = {
    text: <MessageSquare size={10} />,
    confirmation: <CheckSquare size={10} />,
    choice: <Circle size={10} />,
    attachment: <Paperclip size={10} />,
    image: <ImageIcon size={10} />,
    any: <Zap size={10} />,
  }
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 3,
        color: "#999",
        fontSize: 10,
        textTransform: "uppercase",
      }}
    >
      {icons[type]} {type}
    </span>
  )
}

// =====================================================
//  Empty / Loading
// =====================================================
function EmptyBox({ filter, message }: { filter?: string; message?: string }) {
  return (
    <div
      style={{
        background: "rgba(0,0,0,0.2)",
        border: "1px dashed var(--color-hermes-border, #333)",
        borderRadius: 6,
        padding: "30px 20px",
        textAlign: "center",
        color: "var(--color-hermes-text-secondary, #999)",
        fontSize: 13,
      }}
    >
      <Inbox size={24} style={{ opacity: 0.5, marginBottom: 6 }} />
      <div>
        {message ||
          (filter === "open"
            ? "Keine offenen Fragen — alle aktuellen Tasks laufen ohne User-Input."
            : filter === "answered"
            ? "Noch keine beantworteten Fragen."
            : "Keine Fragen gefunden.")}
      </div>
    </div>
  )
}

function LoadingBox() {
  return (
    <div style={{ padding: 20, textAlign: "center", color: "#999" }}>
      <Loader2 size={20} className="spin" />
    </div>
  )
}

// =====================================================
//  Helpers
// =====================================================
function formatAge(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  const ageS = (Date.now() - d.getTime()) / 1000
  if (ageS < 60) return `gerade eben`
  if (ageS < 3600) return `vor ${Math.floor(ageS / 60)} min`
  if (ageS < 86400) return `vor ${Math.floor(ageS / 3600)} h`
  return `vor ${Math.floor(ageS / 86400)} Tagen`
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
