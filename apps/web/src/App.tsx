import { useEffect, useState, type CSSProperties } from "react";
import type {
  AgentFinding,
  ChecklistItem,
  ChecklistItemStatus,
  ChecklistPhase,
  Encounter,
  FindingType,
  Visit,
  VisitDetail,
} from "@abridge/shared";
import { api } from "./api";

// --- design tokens -----------------------------------------------------------

const VISIT_STATUS: Record<string, { label: string; color: string; bg: string }> = {
  active: { label: "Active", color: "#2563eb", bg: "#eff6ff" },
  discharge_planning: { label: "Discharge planning", color: "#d97706", bg: "#fffbeb" },
  discharged: { label: "Discharged", color: "#16a34a", bg: "#f0fdf4" },
};

const FINDING: Record<FindingType, { label: string; color: string; bg: string }> = {
  implicature: { label: "Implicature catch", color: "#7c3aed", bg: "#f5f3ff" },
  med_reconciliation: { label: "Med reconciliation", color: "#0891b2", bg: "#ecfeff" },
  sdoh: { label: "SDOH lookup", color: "#c026d3", bg: "#fdf4ff" },
};

const PHASE_ORDER: ChecklistPhase[] = [
  "initial_assessment",
  "daily",
  "pre_meeting",
  "meeting",
  "day_of_discharge",
];

const PHASE_LABEL: Record<ChecklistPhase, string> = {
  initial_assessment: "Initial nursing assessment",
  daily: "Daily",
  pre_meeting: "Prior to planning meeting",
  meeting: "During planning meeting",
  day_of_discharge: "Day of discharge",
};

// --- shared styles -----------------------------------------------------------

const card: CSSProperties = {
  background: "#fff",
  border: "1px solid #e2e8f0",
  borderRadius: 14,
  padding: 18,
  boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
};

const sectionTitle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.07em",
  textTransform: "uppercase",
  color: "#64748b",
};

function Pill({ label, color, bg }: { label: string; color: string; bg?: string }) {
  return (
    <span
      style={{
        color,
        background: bg ?? "transparent",
        border: bg ? "none" : `1px solid ${color}55`,
        borderRadius: 999,
        padding: "2px 9px",
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: "0.02em",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}

function Chip({ text }: { text: string }) {
  return (
    <span
      style={{
        fontSize: 11,
        color: "#64748b",
        background: "#f1f5f9",
        borderRadius: 6,
        padding: "1px 7px",
        whiteSpace: "nowrap",
      }}
    >
      {text}
    </span>
  );
}

const primaryBtn: CSSProperties = {
  border: "none",
  background: "#4f46e5",
  color: "#fff",
  borderRadius: 8,
  padding: "7px 14px",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};

const ghostBtn: CSSProperties = {
  border: "1px solid #cbd5e1",
  background: "#fff",
  color: "#475569",
  borderRadius: 8,
  padding: "6px 13px",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};

function ProgressBar({ value }: { value: number }) {
  return (
    <div style={{ height: 6, background: "#e2e8f0", borderRadius: 999, overflow: "hidden" }}>
      <div
        style={{
          width: `${Math.round(value * 100)}%`,
          height: "100%",
          background: "#4f46e5",
          borderRadius: 999,
          transition: "width 0.25s ease",
        }}
      />
    </div>
  );
}

// --- review card (agent finding + its proposed action) -----------------------

function ReviewCard({
  item,
  finding,
  onUpdate,
}: {
  item: ChecklistItem;
  finding?: AgentFinding;
  onUpdate: (id: string, status: ChecklistItemStatus) => void;
}) {
  const meta = finding ? FINDING[finding.type] : { label: "Agent", color: "#7c3aed", bg: "#f5f3ff" };
  const isImplicature = finding?.type === "implicature";

  // Route the FHIR task to the discipline that owns it (mockup: SW=rides,
  // Pharm=med-rec). The button label makes the emitted task concrete.
  const owner = item.owner_role ? item.owner_role.replace("_", " ") : "care team";

  const shell: CSSProperties = isImplicature
    ? { background: "#fffbeb", border: "1.5px solid #f59e0b", borderRadius: 12, padding: 16 }
    : { background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: 14 };

  return (
    <div style={shell}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {isImplicature && <span style={{ fontSize: 15 }}>⚠️</span>}
        <Pill
          label={isImplicature ? "Implicature catch — from today’s Abridge transcript" : meta.label}
          color={isImplicature ? "#b45309" : meta.color}
          bg={isImplicature ? "#fef3c7" : meta.bg}
        />
      </div>

      <div style={{ fontWeight: 650, fontSize: 15, marginTop: 8 }}>{finding?.title ?? item.text}</div>
      {finding?.detail && (
        <div style={{ fontSize: 13.5, color: "#475569", marginTop: 2 }}>{finding.detail}</div>
      )}
      {finding?.evidence && (
        <div
          style={{
            fontSize: 12.5,
            color: "#64748b",
            fontStyle: "italic",
            marginTop: 8,
            paddingLeft: 10,
            borderLeft: `2px solid ${isImplicature ? "#f59e0b88" : meta.color + "55"}`,
          }}
        >
          {finding.evidence}
        </div>
      )}
      {finding?.suggested_ask && (
        <div style={{ fontSize: 13, color: "#334155", marginTop: 10 }}>
          <span style={{ color: "#94a3b8", fontWeight: 600 }}>Suggested ask: </span>
          <span style={{ fontStyle: "italic" }}>“{finding.suggested_ask}”</span>
        </div>
      )}

      <div
        style={{
          marginTop: 12,
          paddingTop: 12,
          borderTop: `1px dashed ${isImplicature ? "#fcd34d" : "#e2e8f0"}`,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
        }}
      >
        <div style={{ fontSize: 13, color: "#334155", minWidth: 0 }}>
          <span style={{ color: "#94a3b8", fontWeight: 600 }}>Owner → </span>
          <Chip text={owner} />
        </div>
        <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
          <button style={primaryBtn} onClick={() => onUpdate(item.id, "accepted")}>
            Emit FHIR task ↗
          </button>
          <button style={ghostBtn} onClick={() => onUpdate(item.id, "dismissed")}>
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}

// --- checklist row -----------------------------------------------------------

function ChecklistRow({
  item,
  onUpdate,
}: {
  item: ChecklistItem;
  onUpdate: (id: string, status: ChecklistItemStatus) => void;
}) {
  const done = item.status === "done";
  const dismissed = item.status === "dismissed";
  const toggle = () => onUpdate(item.id, done ? "accepted" : "done");
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "8px 10px",
        borderRadius: 8,
        opacity: dismissed ? 0.5 : 1,
      }}
    >
      <button
        onClick={dismissed ? undefined : toggle}
        title={done ? "Mark not done" : "Mark done"}
        style={{
          width: 20,
          height: 20,
          borderRadius: 6,
          border: `1.5px solid ${done ? "#16a34a" : "#cbd5e1"}`,
          background: done ? "#16a34a" : "#fff",
          color: "#fff",
          cursor: dismissed ? "default" : "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 12,
          flexShrink: 0,
          padding: 0,
        }}
      >
        {done ? "✓" : ""}
      </button>
      <div style={{ flex: 1, minWidth: 0 }}>
        <span
          style={{
            fontSize: 14,
            textDecoration: done ? "line-through" : "none",
            color: done ? "#94a3b8" : "#1e293b",
          }}
        >
          {item.text}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        {item.source === "agent" && <Pill label="agent" color="#7c3aed" bg="#f5f3ff" />}
        {item.owner_role && <Chip text={item.owner_role.replace("_", " ")} />}
      </div>
    </div>
  );
}

// --- captured encounter (expandable transcript) ------------------------------

function EncounterRow({ encounter }: { encounter: Encounter }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const isRounds = encounter.setting === "CARE_CONFERENCE";

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && text === null) {
      setLoading(true);
      try {
        const d = await api.getEncounter(encounter.id);
        setText(d.transcript?.text ?? "");
      } finally {
        setLoading(false);
      }
    }
  };

  const ready = encounter.status === "ready";

  return (
    <div style={{ border: "1px solid #eef2f7", borderRadius: 10, overflow: "hidden" }}>
      <button
        onClick={toggle}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          width: "100%",
          textAlign: "left",
          background: open ? "#f8fafc" : "#fff",
          border: "none",
          padding: "10px 12px",
          cursor: "pointer",
        }}
      >
        <span style={{ color: "#94a3b8", fontSize: 12, width: 12 }}>{open ? "▾" : "▸"}</span>
        {isRounds ? (
          <Pill label="Care conference · rounds" color="#7c3aed" bg="#f5f3ff" />
        ) : (
          <Pill label={`${encounter.setting} · bedside`} color="#0f766e" bg="#f0fdfa" />
        )}
        <span style={{ fontSize: 13.5, color: "#334155" }}>{encounter.clinician.name}</span>
        {!ready && <Pill label={encounter.status} color="#d97706" bg="#fffbeb" />}
        <span style={{ fontSize: 12.5, color: "#94a3b8", marginLeft: "auto" }}>
          {new Date(encounter.started_at).toLocaleString("en-US", {
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
          })}
        </span>
      </button>
      {open && (
        <div style={{ padding: "0 12px 12px" }}>
          {loading ? (
            <div style={{ fontSize: 13, color: "#94a3b8" }}>Loading transcript…</div>
          ) : (
            <pre
              style={{
                whiteSpace: "pre-wrap",
                fontFamily: "inherit",
                fontSize: 13,
                lineHeight: 1.55,
                color: "#334155",
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 8,
                padding: 12,
                margin: 0,
                maxHeight: 280,
                overflow: "auto",
              }}
            >
              {text || "(no transcript yet)"}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// --- sync pipeline (ambient → EHR → agent → diff to approve) ------------------

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const SYNC_STEPS = [
  { icon: "🎙", title: "Read ambient capture" },
  { icon: "📋", title: "Pull EHR context — orders · meds · criteria" },
  { icon: "🧠", title: "Reasoning agent — Claude Opus 4.8" },
  { icon: "✅", title: "Propose IDEAL discharge updates" },
];

function StepRow({
  icon,
  title,
  sub,
  state,
}: {
  icon: string;
  title: string;
  sub?: string;
  state: "pending" | "running" | "done";
}) {
  const color = state === "done" ? "#16a34a" : state === "running" ? "#4f46e5" : "#cbd5e1";
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "flex-start", padding: "10px 0" }}>
      <div
        style={{
          width: 26,
          height: 26,
          borderRadius: 999,
          border: `2px solid ${color}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 13,
          flexShrink: 0,
          color,
          background: state === "done" ? "#f0fdf4" : "#fff",
        }}
      >
        {state === "done" ? "✓" : state === "running" ? <Spinner /> : icon}
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: state === "pending" ? "#94a3b8" : "#1e293b" }}>
          {title}
        </div>
        {sub && state !== "pending" && (
          <div style={{ fontSize: 12.5, color: "#64748b", marginTop: 2 }}>{sub}</div>
        )}
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <span
      style={{
        width: 12,
        height: 12,
        border: "2px solid #c7d2fe",
        borderTopColor: "#4f46e5",
        borderRadius: 999,
        display: "inline-block",
        animation: "abspin 0.7s linear infinite",
      }}
    />
  );
}

function SyncModal({
  visit,
  step,
  findingById,
  onApprove,
  onDismiss,
  onApproveAll,
  onClose,
  busy,
}: {
  visit: VisitDetail;
  step: number;
  findingById: (id: string | null) => AgentFinding | undefined;
  onApprove: (id: string) => void;
  onDismiss: (id: string) => void;
  onApproveAll: () => void;
  onClose: () => void;
  busy: boolean;
}) {
  const proposed = visit.checklist.filter((i) => i.status === "proposed");
  const proposedSorted = [...proposed].sort((a, b) => {
    const rank = (i: ChecklistItem) => (findingById(i.finding_id)?.type === "implicature" ? 0 : 1);
    return rank(a) - rank(b);
  });
  const subs = [
    `${visit.encounters.length} encounter(s): ${visit.encounters
      .map((e) => (e.setting === "CARE_CONFERENCE" ? "rounds" : "bedside"))
      .join(", ")}`,
    visit.patient.chart_summary || "chart summary",
    "reasoning over transcripts + chart + SDOH profile",
    step >= 3 ? `${proposed.length} proposed change(s) to review` : "",
  ];
  const stepState = (i: number): "pending" | "running" | "done" =>
    step > i ? "done" : step === i ? (i === 3 ? "done" : "running") : "pending";

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15,23,42,0.45)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: "6vh 16px",
        zIndex: 50,
        overflow: "auto",
      }}
      onClick={onClose}
    >
      <div
        style={{ ...card, width: "100%", maxWidth: 640, padding: 22 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 700, color: "#0f172a" }}>
              Updating discharge plan
            </div>
            <div style={{ fontSize: 13, color: "#64748b" }}>{visit.patient.display_name}</div>
          </div>
          <button style={ghostBtn} onClick={onClose}>
            Close
          </button>
        </div>

        <div style={{ marginTop: 12, borderTop: "1px solid #f1f5f9", paddingTop: 6 }}>
          {SYNC_STEPS.map((s, i) => (
            <StepRow key={i} icon={s.icon} title={s.title} sub={subs[i]} state={stepState(i)} />
          ))}
        </div>

        {step >= 3 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div style={{ ...sectionTitle, color: "#7c3aed" }}>
                Δ Proposed updates to the IDEAL plan
              </div>
              {proposedSorted.length > 0 && (
                <button style={busy ? { ...primaryBtn, opacity: 0.6 } : primaryBtn} onClick={onApproveAll} disabled={busy}>
                  Approve all &amp; emit tasks
                </button>
              )}
            </div>
            {proposedSorted.length === 0 ? (
              <div
                style={{
                  fontSize: 14,
                  color: "#16a34a",
                  background: "#f0fdf4",
                  border: "1px solid #bbf7d0",
                  borderRadius: 10,
                  padding: 14,
                  fontWeight: 600,
                }}
              >
                ✓ All changes applied to the discharge plan.
              </div>
            ) : (
              <div style={{ display: "grid", gap: 10 }}>
                {proposedSorted.map((item) => (
                  <ReviewCard
                    key={item.id}
                    item={item}
                    finding={findingById(item.finding_id)}
                    onUpdate={(id, status) => (status === "accepted" ? onApprove(id) : onDismiss(id))}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// --- visit detail ------------------------------------------------------------

function VisitPanel({ visit, onChanged }: { visit: VisitDetail; onChanged: (v: VisitDetail) => void }) {
  const [addingRounds, setAddingRounds] = useState(false);
  const [notingBusy, setNotingBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncStep, setSyncStep] = useState(0);
  const [syncBusy, setSyncBusy] = useState(false);

  // The star of the demo: a visible pipeline — read ambient capture, pull EHR
  // context, run the reasoning agent, then surface the plan changes as a diff
  // the SW approves. Steps 0-1 animate; step 2 is the real Claude call.
  const startSync = async () => {
    setSyncing(true);
    setSyncStep(0);
    try {
      await sleep(850);
      setSyncStep(1);
      await sleep(850);
      setSyncStep(2);
      onChanged(await api.runReasoning(visit.id));
      setSyncStep(3);
    } catch {
      setSyncing(false);
    }
  };

  const approveAll = async () => {
    setSyncBusy(true);
    try {
      const proposed = visit.checklist.filter((i) => i.status === "proposed");
      for (const item of proposed) {
        await api.updateChecklistItem(item.id, "accepted");
      }
      onChanged(await api.getVisit(visit.id));
    } finally {
      setSyncBusy(false);
    }
  };

  const addRounds = async () => {
    setAddingRounds(true);
    try {
      onChanged(await api.addCareConference(visit.id));
    } finally {
      setAddingRounds(false);
    }
  };

  const genNote = async () => {
    setNotingBusy(true);
    try {
      onChanged(await api.generateEhrNote(visit.id));
    } finally {
      setNotingBusy(false);
    }
  };

  const fileNote = async (noteId: string) => {
    setNotingBusy(true);
    try {
      await api.fileEhrNote(noteId);
      onChanged(await api.getVisit(visit.id));
    } finally {
      setNotingBusy(false);
    }
  };

  const updateItem = async (id: string, status: ChecklistItemStatus) => {
    await api.updateChecklistItem(id, status);
    onChanged(await api.getVisit(visit.id));
  };

  const status = VISIT_STATUS[visit.status];
  const planItems = visit.checklist.filter((i) => i.status !== "proposed" && i.status !== "dismissed");
  const doneCount = planItems.filter((i) => i.status === "done").length;
  const progress = planItems.length ? doneCount / planItems.length : 0;
  const findingById = (id: string | null) => visit.findings.find((f) => f.id === id);
  const hasRounds = visit.encounters.some((e) => e.setting === "CARE_CONFERENCE");
  const note = visit.ehr_note;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {/* header */}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
          <div>
            <h2 style={{ fontSize: 22 }}>{visit.patient.display_name}</h2>
            <div style={{ color: "#64748b", fontSize: 14, marginTop: 2 }}>
              {visit.primary_diagnosis}
            </div>
            <div style={{ color: "#94a3b8", fontSize: 12.5, marginTop: 3 }}>
              MRN {visit.patient.mrn}
              {visit.patient.gender ? ` · ${visit.patient.gender}` : ""}
              {visit.patient.chart_summary ? ` · ${visit.patient.chart_summary}` : ""}
            </div>
          </div>
          <Pill label={status.label} color={status.color} bg={status.bg} />
        </div>
        <div style={{ marginTop: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 6 }}>
            <span style={{ color: "#64748b", fontWeight: 600 }}>Discharge plan progress</span>
            <span style={{ color: "#334155", fontWeight: 600 }}>
              {doneCount} of {planItems.length} complete
            </span>
          </div>
          <ProgressBar value={progress} />
        </div>
        <button
          onClick={startSync}
          disabled={syncing}
          style={{
            marginTop: 16,
            width: "100%",
            border: "none",
            background: "linear-gradient(90deg,#4f46e5,#7c3aed)",
            color: "#fff",
            borderRadius: 10,
            padding: "12px 16px",
            fontSize: 14.5,
            fontWeight: 700,
            cursor: syncing ? "default" : "pointer",
            opacity: syncing ? 0.7 : 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
          }}
        >
          ⟳ Update discharge plan from new capture
        </button>
        <div style={{ fontSize: 11.5, color: "#94a3b8", marginTop: 6, textAlign: "center" }}>
          Reads ambient capture + EHR context, runs the reasoning agent, and shows the plan changes to approve.
        </div>
      </div>

      {syncing && (
        <SyncModal
          visit={visit}
          step={syncStep}
          findingById={findingById}
          onApprove={(id) => updateItem(id, "accepted")}
          onDismiss={(id) => updateItem(id, "dismissed")}
          onApproveAll={approveAll}
          onClose={() => setSyncing(false)}
          busy={syncBusy}
        />
      )}

      {/* IDEAL discharge plan — the object the agent updates */}
      <div style={card}>
        <div style={sectionTitle}>IDEAL discharge plan</div>
        {PHASE_ORDER.map((phase) => {
          const rows = planItems.filter((i) => i.phase === phase);
          if (rows.length === 0) return null;
          const d = rows.filter((i) => i.status === "done").length;
          return (
            <div key={phase} style={{ marginTop: 16 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  paddingBottom: 6,
                  borderBottom: "1px solid #f1f5f9",
                }}
              >
                <span style={{ fontSize: 13, fontWeight: 700, color: "#334155" }}>{PHASE_LABEL[phase]}</span>
                <span style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600 }}>
                  {d}/{rows.length}
                </span>
              </div>
              <div style={{ marginTop: 4 }}>
                {rows.map((item) => (
                  <ChecklistRow key={item.id} item={item} onUpdate={updateItem} />
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* encounters — click to read the captured transcript */}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div style={sectionTitle}>Ambient capture · {visit.encounters.length}</div>
          <button
            style={addingRounds ? { ...ghostBtn, opacity: 0.6 } : ghostBtn}
            onClick={addRounds}
            disabled={addingRounds}
            title="Capture the provider↔provider rounds discussion (mic-free fallback; iOS records this live)"
          >
            {addingRounds ? "Capturing…" : hasRounds ? "＋ Re-capture rounds" : "🎙 Capture rounds"}
          </button>
        </div>
        <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>
          Bedside + rounds transcripts feeding the agent — click any to read.
        </div>
        <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
          {visit.encounters.map((e) => (
            <EncounterRow key={e.id} encounter={e} />
          ))}
        </div>
      </div>

      {/* EHR note — the daily SW note that gets filed to the chart */}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div style={sectionTitle}>EHR note → chart</div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {note?.status === "filed" && (
              <Pill label={`Filed ${new Date(note.filed_at ?? note.created_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`} color="#16a34a" bg="#f0fdf4" />
            )}
            <button
              style={notingBusy ? { ...ghostBtn, opacity: 0.6 } : ghostBtn}
              onClick={genNote}
              disabled={notingBusy}
            >
              {notingBusy ? "Working…" : note ? "Regenerate note" : "Generate EHR note"}
            </button>
            {note && note.status !== "filed" && (
              <button
                style={notingBusy ? { ...primaryBtn, opacity: 0.6 } : primaryBtn}
                onClick={() => fileNote(note.id)}
                disabled={notingBusy}
              >
                File to EHR chart ↗
              </button>
            )}
          </div>
        </div>
        {note ? (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 11, color: "#94a3b8", marginBottom: 8, fontWeight: 600 }}>
              {note.status === "filed" ? "Filed to chart" : "Draft — review before filing"}
              {note.model ? ` · drafted by ${note.model}` : ""}
            </div>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                fontFamily: "inherit",
                fontSize: 13,
                lineHeight: 1.55,
                color: "#334155",
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 10,
                padding: 14,
                margin: 0,
                maxHeight: note.status === "filed" ? 200 : undefined,
                overflow: "auto",
              }}
            >
              {note.text}
            </pre>
          </div>
        ) : (
          <p style={{ color: "#94a3b8", fontSize: 14, marginTop: 10 }}>
            No note yet. Generate an up-to-date discharge-planning note from the captured encounters, chart, and the approved plan.
          </p>
        )}
      </div>
    </div>
  );
}

// --- sidebar visit card ------------------------------------------------------

function VisitCard({ visit, selected, onClick }: { visit: Visit; selected: boolean; onClick: () => void }) {
  const status = VISIT_STATUS[visit.status];
  return (
    <button
      onClick={onClick}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        background: "#fff",
        border: `1px solid ${selected ? "#4f46e5" : "#e2e8f0"}`,
        boxShadow: selected ? "0 0 0 3px #4f46e522" : "0 1px 2px rgba(15,23,42,0.04)",
        borderRadius: 12,
        padding: 14,
        marginBottom: 10,
        cursor: "pointer",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <strong style={{ fontSize: 15, color: "#0f172a" }}>{visit.patient.display_name}</strong>
        <Pill label={status.label} color={status.color} bg={status.bg} />
      </div>
      <div style={{ color: "#64748b", fontSize: 13, marginTop: 4 }}>{visit.primary_diagnosis}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
        {visit.proposed_count > 0 && (
          <Pill label={`${visit.proposed_count} to review`} color="#7c3aed" bg="#f5f3ff" />
        )}
        <span style={{ fontSize: 12, color: "#94a3b8" }}>
          {visit.open_item_count} open · {visit.encounter_count} encounters
        </span>
      </div>
    </button>
  );
}

// --- app shell ---------------------------------------------------------------

export default function App() {
  const [health, setHealth] = useState("checking…");
  const [visits, setVisits] = useState<Visit[]>([]);
  const [selected, setSelected] = useState<VisitDetail | null>(null);

  const loadVisits = () => api.listVisits().then(setVisits).catch(() => {});

  useEffect(() => {
    api.health().then((h) => setHealth(h.status)).catch(() => setHealth("unreachable"));
    api
      .listVisits()
      .then((vs) => {
        setVisits(vs);
        if (vs[0]) api.getVisit(vs[0].id).then(setSelected); // open the first visit
      })
      .catch(() => {});
  }, []);

  const onChanged = (v: VisitDetail) => {
    setSelected(v);
    loadVisits();
  };

  const healthy = health === "ok";

  return (
    <div style={{ minHeight: "100vh" }}>
      {/* top bar */}
      <header
        style={{
          background: "#fff",
          borderBottom: "1px solid #e2e8f0",
          padding: "14px 24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          position: "sticky",
          top: 0,
          zIndex: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{ fontSize: 17, fontWeight: 700, color: "#0f172a" }}>Abridge</span>
          <span style={{ fontSize: 14, color: "#64748b" }}>Care Coordination</span>
        </div>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "#64748b" }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 999,
              background: healthy ? "#16a34a" : "#dc2626",
            }}
          />
          API {health}
        </span>
      </header>

      <div
        style={{
          maxWidth: 1200,
          margin: "0 auto",
          padding: 24,
          display: "grid",
          gridTemplateColumns: "300px 1fr",
          gap: 24,
          alignItems: "start",
        }}
      >
        {/* sidebar */}
        <aside style={{ position: "sticky", top: 88 }}>
          <div style={{ ...sectionTitle, marginBottom: 12 }}>Visits · {visits.length}</div>
          {visits.length === 0 && <p style={{ color: "#94a3b8", fontSize: 14 }}>No visits yet.</p>}
          {visits.map((v) => (
            <VisitCard
              key={v.id}
              visit={v}
              selected={selected?.id === v.id}
              onClick={() => api.getVisit(v.id).then(setSelected)}
            />
          ))}
        </aside>

        {/* detail */}
        <main>
          {selected ? (
            <VisitPanel visit={selected} onChanged={onChanged} />
          ) : (
            <div style={{ ...card, color: "#94a3b8", textAlign: "center", padding: 48 }}>
              Select a visit to review its discharge plan.
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
