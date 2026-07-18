import { useEffect, useState } from "react";
import type { Encounter, EncounterDetail } from "@abridge/shared";
import { api } from "./api";

const STATUS_COLOR: Record<string, string> = {
  recording: "#b45309",
  uploaded: "#2563eb",
  transcribing: "#2563eb",
  ready: "#15803d",
  failed: "#b91c1c",
};

export default function App() {
  const [health, setHealth] = useState<string>("checking…");
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [selected, setSelected] = useState<EncounterDetail | null>(null);

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth(h.status))
      .catch(() => setHealth("api unreachable"));
    const load = () => api.listEncounters().then(setEncounters).catch(() => {});
    load();
    const t = setInterval(load, 4000); // keep the review list fresh
    return () => clearInterval(t);
  }, []);

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 720, margin: "3rem auto", padding: "0 1rem" }}>
      <h1>Abridge — Encounter Review</h1>
      <p>
        API status: <strong>{health}</strong>
      </p>

      {encounters.length === 0 && <p style={{ color: "#9ca3af" }}>No encounters yet.</p>}

      <ul style={{ listStyle: "none", padding: 0 }}>
        {encounters.map((e) => (
          <li
            key={e.id}
            onClick={() => api.getEncounter(e.id).then(setSelected)}
            style={{
              border: "1px solid #e5e7eb",
              borderRadius: 10,
              padding: "12px 14px",
              marginBottom: 10,
              cursor: "pointer",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <strong>{e.patient.display_name}</strong>
              <span style={{ color: STATUS_COLOR[e.status], fontWeight: 700, fontSize: 12, textTransform: "uppercase" }}>
                {e.status}
              </span>
            </div>
            <div style={{ color: "#6b7280", fontSize: 13, marginTop: 4 }}>
              {e.setting} · {e.clinician.name} · {new Date(e.started_at).toLocaleString()}
            </div>
          </li>
        ))}
      </ul>

      {selected && (
        <div style={{ marginTop: 24, borderTop: "2px solid #111", paddingTop: 16 }}>
          <h2 style={{ marginBottom: 4 }}>
            {selected.patient.display_name} · {selected.setting}
          </h2>
          <p style={{ color: "#6b7280", marginTop: 0 }}>
            {selected.clinician.name} · MRN {selected.patient.mrn}
          </p>
          <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
            {selected.transcript?.text ?? "(no transcript yet)"}
          </p>
        </div>
      )}
    </main>
  );
}
