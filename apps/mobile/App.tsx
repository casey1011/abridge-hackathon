import { StatusBar } from "expo-status-bar";
import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import type {
  Clinician,
  Encounter,
  EncounterSetting,
  EncounterStatus,
  Patient,
  Visit,
} from "@abridge/shared";
import { api } from "./src/api";

const SETTINGS: EncounterSetting[] = ["ED", "INPATIENT", "HOME", "CARE_CONFERENCE"];

const SETTING_LABEL: Record<EncounterSetting, string> = {
  ED: "ED",
  INPATIENT: "Inpatient",
  HOME: "Home",
  CARE_CONFERENCE: "Care conference (rounds)",
};

const STATUS_COLOR: Record<EncounterStatus, string> = {
  recording: "#b45309",
  uploaded: "#2563eb",
  transcribing: "#2563eb",
  ready: "#15803d",
  failed: "#b91c1c",
};

export default function App() {
  const [health, setHealth] = useState("checking…");
  const [clinicians, setClinicians] = useState<Clinician[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [visits, setVisits] = useState<Visit[]>([]);
  const [encounters, setEncounters] = useState<Encounter[]>([]);

  const [clinicianId, setClinicianId] = useState<string>();
  const [patientId, setPatientId] = useState<string>();
  const [visitId, setVisitId] = useState<string>();
  const [setting, setSetting] = useState<EncounterSetting>("ED");

  const [busy, setBusy] = useState(false); // creating / uploading / polling
  const [activeId, setActiveId] = useState<string>(); // encounter being recorded

  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth(h.status))
      .catch(() => setHealth("api unreachable"));
    api.listClinicians().then((c) => {
      setClinicians(c);
      setClinicianId((id) => id ?? c[0]?.id);
    });
    api.listPatients().then(setPatients).catch(() => {});
    api.listVisits().then(setVisits).catch(() => {});
    refreshEncounters();
  }, []);

  function refreshEncounters() {
    api.listEncounters().then(setEncounters).catch(() => {});
  }

  async function startRecording() {
    const isRounds = setting === "CARE_CONFERENCE";
    // A rounds meeting is about a specific stay — its patient comes from the visit.
    const roundsVisit = visits.find((v) => v.id === visitId);
    const effectivePatientId = isRounds ? roundsVisit?.patient.id : patientId;

    if (!clinicianId) {
      Alert.alert("Pick a clinician first");
      return;
    }
    if (isRounds && !roundsVisit) {
      Alert.alert("Pick the visit these rounds are about");
      return;
    }
    if (!effectivePatientId) {
      Alert.alert("Pick a patient first");
      return;
    }
    const perm = await AudioModule.requestRecordingPermissionsAsync();
    if (!perm.granted) {
      Alert.alert("Microphone permission is required to record.");
      return;
    }
    setBusy(true);
    try {
      const enc = await api.createEncounter({
        patient_id: effectivePatientId,
        clinician_id: clinicianId,
        setting,
        visit_id: isRounds ? visitId : visitId ?? null,
      });
      setActiveId(enc.id);
      await setAudioModeAsync({ playsInSilentMode: true, allowsRecording: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      refreshEncounters();
    } catch (e) {
      Alert.alert("Could not start recording", String(e));
    } finally {
      setBusy(false);
    }
  }

  async function stopAndSave() {
    if (!activeId) return;
    setBusy(true);
    try {
      const durationSeconds = recorderState.durationMillis
        ? recorderState.durationMillis / 1000
        : undefined;
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) throw new Error("no recording file produced");
      await api.uploadRecording(activeId, uri, durationSeconds);
      await pollUntilDone(activeId);
    } catch (e) {
      Alert.alert("Upload failed", String(e));
    } finally {
      setActiveId(undefined);
      setBusy(false);
      refreshEncounters();
    }
  }

  // Poll the encounter until transcription resolves (ready/failed) or times out.
  async function pollUntilDone(id: string) {
    for (let i = 0; i < 20; i++) {
      const enc = await api.getEncounter(id);
      setEncounters((prev) =>
        prev.map((e) => (e.id === id ? enc : e)),
      );
      if (enc.status === "ready" || enc.status === "failed") return;
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  const recording = !!activeId;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Text style={styles.h1}>Ruby</Text>
      <Text style={styles.status}>API: {health}</Text>

      {/* Clinician */}
      <Text style={styles.label}>Clinician</Text>
      <View style={styles.pillRow}>
        {clinicians.map((c) => (
          <Pill
            key={c.id}
            text={c.name}
            active={c.id === clinicianId}
            disabled={recording}
            onPress={() => setClinicianId(c.id)}
          />
        ))}
      </View>

      {/* Patient — bedside encounters only; a rounds meeting gets its patient
          from the chosen visit, so we don't ask twice. */}
      {setting !== "CARE_CONFERENCE" && (
        <>
          <Text style={styles.label}>Patient</Text>
          <View style={styles.pillRow}>
            {patients.map((p) => (
              <Pill
                key={p.id}
                text={`${p.display_name} · ${p.mrn}`}
                active={p.id === patientId}
                disabled={recording}
                onPress={() => setPatientId(p.id)}
              />
            ))}
          </View>
        </>
      )}

      {/* Setting */}
      <Text style={styles.label}>Setting</Text>
      <View style={styles.pillRow}>
        {SETTINGS.map((s) => (
          <Pill
            key={s}
            text={SETTING_LABEL[s]}
            active={s === setting}
            disabled={recording}
            onPress={() => setSetting(s)}
          />
        ))}
      </View>

      {/* Visit picker — required for a care-conference (rounds about a stay) */}
      {setting === "CARE_CONFERENCE" && (
        <>
          <Text style={styles.label}>Which patient are these rounds about?</Text>
          <View style={styles.pillRow}>
            {visits.map((v) => (
              <Pill
                key={v.id}
                text={`${v.patient.display_name} · ${v.primary_diagnosis}`}
                active={v.id === visitId}
                disabled={recording}
                onPress={() => setVisitId(v.id)}
              />
            ))}
          </View>
        </>
      )}

      {/* Record control */}
      {!recording ? (
        <TouchableOpacity
          style={[styles.recordBtn, busy && styles.btnDisabled]}
          onPress={startRecording}
          disabled={busy}
        >
          <Text style={styles.recordBtnText}>● Start recording</Text>
        </TouchableOpacity>
      ) : (
        <TouchableOpacity
          style={[styles.stopBtn, busy && styles.btnDisabled]}
          onPress={stopAndSave}
          disabled={busy}
        >
          <Text style={styles.recordBtnText}>
            ■ Stop & save{"  "}
            {formatDuration(recorderState.durationMillis)}
          </Text>
        </TouchableOpacity>
      )}
      {busy && <ActivityIndicator style={{ marginTop: 12 }} />}

      {/* Recent encounters */}
      <Text style={[styles.label, { marginTop: 28 }]}>Recent encounters</Text>
      {encounters.length === 0 && (
        <Text style={styles.empty}>No encounters yet.</Text>
      )}
      {encounters.map((e) => (
        <EncounterRow key={e.id} encounter={e} />
      ))}

      <StatusBar style="auto" />
    </ScrollView>
  );
}

function EncounterRow({ encounter }: { encounter: Encounter }) {
  const [transcript, setTranscript] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  async function toggle() {
    if (!open && encounter.status === "ready" && transcript === null) {
      const detail = await api.getEncounter(encounter.id);
      setTranscript(detail.transcript?.text ?? "");
    }
    setOpen((o) => !o);
  }

  return (
    <TouchableOpacity style={styles.card} onPress={toggle} activeOpacity={0.7}>
      <View style={styles.cardHead}>
        <Text style={styles.cardTitle}>{encounter.patient.display_name}</Text>
        <Text style={[styles.chip, { color: STATUS_COLOR[encounter.status] }]}>
          {encounter.status}
        </Text>
      </View>
      <Text style={styles.cardMeta}>
        {SETTING_LABEL[encounter.setting]} · {encounter.clinician.name} ·{" "}
        {new Date(encounter.started_at).toLocaleTimeString()}
      </Text>
      {open && transcript !== null && (
        <Text style={styles.transcript}>{transcript || "(empty transcript)"}</Text>
      )}
    </TouchableOpacity>
  );
}

function Pill({
  text,
  active,
  disabled,
  onPress,
}: {
  text: string;
  active: boolean;
  disabled?: boolean;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity
      style={[styles.pill, active && styles.pillActive, disabled && styles.pillDisabled]}
      onPress={onPress}
      disabled={disabled}
    >
      <Text style={[styles.pillText, active && styles.pillTextActive]}>{text}</Text>
    </TouchableOpacity>
  );
}

function formatDuration(ms?: number): string {
  const total = Math.floor((ms ?? 0) / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#fff" },
  content: { paddingTop: 72, paddingHorizontal: 20, paddingBottom: 48 },
  h1: { fontSize: 24, fontWeight: "700" },
  status: { color: "#555", marginBottom: 20 },
  label: { fontSize: 13, fontWeight: "600", color: "#374151", marginBottom: 8, marginTop: 12 },
  pillRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  pill: {
    borderWidth: 1,
    borderColor: "#d1d5db",
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 14,
  },
  pillActive: { backgroundColor: "#111", borderColor: "#111" },
  pillDisabled: { opacity: 0.4 },
  pillText: { color: "#111", fontSize: 14 },
  pillTextActive: { color: "#fff", fontWeight: "600" },
  recordBtn: {
    marginTop: 24,
    backgroundColor: "#b91c1c",
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: "center",
  },
  stopBtn: {
    marginTop: 24,
    backgroundColor: "#111",
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: "center",
  },
  btnDisabled: { opacity: 0.5 },
  recordBtnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  empty: { color: "#9ca3af", marginTop: 4 },
  card: {
    borderWidth: 1,
    borderColor: "#e5e7eb",
    borderRadius: 12,
    padding: 14,
    marginTop: 10,
  },
  cardHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  cardTitle: { fontSize: 16, fontWeight: "600" },
  chip: { fontSize: 12, fontWeight: "700", textTransform: "uppercase" },
  cardMeta: { color: "#6b7280", fontSize: 13, marginTop: 4 },
  transcript: { marginTop: 10, color: "#111", fontSize: 14, lineHeight: 20 },
});
