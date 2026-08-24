import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

const PROCESSING = new Set(["queued", "transcribing", "summarizing"]);

function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return "";
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatTime(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatDate(value) {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function statusLabel(status) {
  return {
    queued: "Queued",
    transcribing: "Transcribing",
    summarizing: "Writing minutes",
    completed: "Ready",
    failed: "Failed",
  }[status] || status;
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [meetings, setMeetings] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [tab, setTab] = useState("minutes");
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [keySaving, setKeySaving] = useState(false);
  const [keyMessage, setKeyMessage] = useState("");
  const inputRef = useRef(null);

  const refreshList = useCallback(async () => {
    const items = await api.listMeetings();
    setMeetings(items);
    return items;
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    refreshList().catch((err) => setError(err.message));
  }, [refreshList]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return undefined;
    }
    let cancelled = false;
    let interval;
    const tick = async () => {
      try {
        const data = await api.getMeeting(selectedId);
        if (cancelled) return false;
        setDetail(data);
        return PROCESSING.has(data.status);
      } catch (err) {
        if (!cancelled) setError(err.message);
        return false;
      }
    };
    (async () => {
      const keepGoing = await tick();
      if (keepGoing && !cancelled) {
        interval = setInterval(async () => {
          const stillBusy = await tick();
          if (!stillBusy && interval) {
            clearInterval(interval);
            interval = null;
            refreshList().catch(() => {});
          }
        }, 1500);
      }
    })();
    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
  }, [selectedId, refreshList]);

  useEffect(() => {
    const busy = meetings.some((item) => PROCESSING.has(item.status));
    if (!busy) return undefined;
    const timer = setInterval(() => {
      refreshList().catch(() => {});
    }, 2000);
    return () => clearInterval(timer);
  }, [meetings, refreshList]);

  async function handleFiles(fileList) {
    const file = fileList?.[0];
    if (!file) return;
    setError("");
    setUploading(true);
    setProgress(0);
    try {
      const created = await api.uploadMeeting(file, setProgress);
      await refreshList();
      setSelectedId(created.id);
      setDetail(created);
      setTab("minutes");
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  async function onToggle(action) {
    if (!detail) return;
    const updated = await api.toggleAction(detail.id, action.id, !action.done);
    setDetail(updated);
  }

  async function onDelete() {
    if (!detail) return;
    if (!window.confirm("Delete this meeting and its audio?")) return;
    await api.deleteMeeting(detail.id);
    setSelectedId(null);
    setDetail(null);
    await refreshList();
  }

  function copy(text) {
    navigator.clipboard.writeText(text);
  }

  async function onSaveKey(event) {
    event.preventDefault();
    if (!apiKey.trim()) return;
    setKeySaving(true);
    setKeyMessage("");
    setError("");
    try {
      const result = await api.saveOpenAIKey(apiKey.trim());
      setHealth((current) => ({
        ...(current || {}),
        demo_mode: result.demo_mode,
        has_api_key: result.has_api_key,
        key_hint: result.key_hint,
      }));
      setApiKey("");
      setKeyMessage(
        result.verified
          ? `Live Whisper is on (${result.key_hint}).`
          : `Key saved as ${result.key_hint}. OpenAI could not be reached to verify it.`
      );
    } catch (err) {
      setKeyMessage(err.message);
    } finally {
      setKeySaving(false);
    }
  }

  async function onClearKey() {
    setKeySaving(true);
    setKeyMessage("");
    try {
      const result = await api.clearOpenAIKey();
      setHealth((current) => ({
        ...(current || {}),
        demo_mode: result.demo_mode,
        has_api_key: result.has_api_key,
        key_hint: result.key_hint,
      }));
      setApiKey("");
      setKeyMessage("Key removed. Demo mode is back on.");
    } catch (err) {
      setKeyMessage(err.message);
    } finally {
      setKeySaving(false);
    }
  }

  const minutesText = detail?.summary
    ? [
        detail.title,
        "",
        detail.summary.overview,
        "",
        "Key decisions",
        ...(detail.summary.key_decisions || []).map((item) => `- ${item}`),
        "",
        "Action items",
        ...(detail.action_items || []).map(
          (item) =>
            `- ${item.task}${item.owner ? ` (${item.owner})` : ""}${item.due ? ` — ${item.due}` : ""}`
        ),
      ].join("\n")
    : "";

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="mark">m</div>
          <div>
            <h1>Minute</h1>
            <p>Audio to action items</p>
          </div>
        </div>
        {health?.demo_mode ? (
          <div className="demo-chip">Demo mode — add an OpenAI key below</div>
        ) : (
          <div className="demo-chip live">Live Whisper · {health?.key_hint}</div>
        )}
        <div className="meeting-list">
          <div className="list-label">Meetings</div>
          {meetings.length === 0 ? (
            <div className="meeting-row">
              <span>No recordings yet. Drop a file on the right.</span>
            </div>
          ) : (
            meetings.map((item) => (
              <button
                key={item.id}
                className={`meeting-row ${item.id === selectedId ? "active" : ""}`}
                onClick={() => {
                  setSelectedId(item.id);
                  setTab("minutes");
                }}
              >
                <strong>{item.title}</strong>
                <span>
                  {formatDate(item.created_at)}
                  {item.duration_seconds ? ` · ${formatDuration(item.duration_seconds)}` : ""}
                  {` · ${statusLabel(item.status)}`}
                </span>
              </button>
            ))
          )}
        </div>
        <form className="key-form" onSubmit={onSaveKey}>
          <div className="list-label">OpenAI API key</div>
          <input
            type="password"
            autoComplete="off"
            placeholder={health?.has_api_key ? `Replace ${health.key_hint}` : "sk-…"}
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
          />
          <div className="key-actions">
            <button className="primary" type="submit" disabled={keySaving || !apiKey.trim()}>
              {keySaving ? "Saving…" : "Save key"}
            </button>
            {health?.has_api_key ? (
              <button className="ghost" type="button" onClick={onClearKey} disabled={keySaving}>
                Remove
              </button>
            ) : null}
          </div>
          {keyMessage ? <p className="key-note">{keyMessage}</p> : null}
        </form>
      </aside>

      <main className="workspace">
        <div className="topbar">
          <div>
            <p className="eyebrow">Meeting summarizer</p>
            <h2>{detail ? detail.title : "Drop in a recording"}</h2>
          </div>
          <button className="primary" onClick={() => inputRef.current?.click()}>
            Upload audio
          </button>
        </div>

        {error ? <div className="error-box">{error}</div> : null}

        {!detail ? (
          <div
            className={`panel dropzone ${dragOver ? "over" : ""}`}
            role="button"
            tabIndex={0}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
            }}
            onDragOver={(event) => {
              event.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragOver(false);
              handleFiles(event.dataTransfer.files);
            }}
          >
            <div className="wave" aria-hidden="true">
              <i /><i /><i /><i /><i /><i /><i />
            </div>
            <h3>{uploading ? "Uploading…" : "Upload meeting audio"}</h3>
            <p>
              mp3, wav, m4a, mp4, webm, ogg, flac — up to {health?.max_upload_mb || 25}MB.
              Whisper transcribes it, then an LLM writes decisions and tasks.
            </p>
            <span className="ghost">Choose a file</span>
            {uploading ? (
              <div className="progress">
                <b style={{ width: `${progress}%` }} />
              </div>
            ) : null}
          </div>
        ) : (
          <section className="panel detail">
            <div className="meta-row">
              <span className={`status-chip ${detail.status}`}>{statusLabel(detail.status)}</span>
              <span className="status-chip">{detail.original_filename}</span>
              {detail.language ? <span className="status-chip">{detail.language}</span> : null}
              {detail.duration_seconds ? (
                <span className="status-chip">{formatDuration(detail.duration_seconds)}</span>
              ) : null}
              {detail.demo_mode ? <span className="status-chip">Sample pipeline</span> : null}
            </div>

            {detail.error_message ? <div className="error-box">{detail.error_message}</div> : null}

            <div className="tabs">
              {["minutes", "transcript", "audio"].map((name) => (
                <button
                  key={name}
                  className={`tab ${tab === name ? "active" : ""}`}
                  onClick={() => setTab(name)}
                >
                  {name[0].toUpperCase() + name.slice(1)}
                </button>
              ))}
              <span style={{ flex: 1 }} />
              <button className="ghost" onClick={() => setSelectedId(null)}>
                New upload
              </button>
              <button className="danger" onClick={onDelete}>
                Delete
              </button>
            </div>

            {PROCESSING.has(detail.status) ? (
              <div className="section">
                <div className="wave">
                  <i /><i /><i /><i /><i /><i /><i />
                </div>
                <p className="empty">
                  {detail.status === "transcribing"
                    ? "Listening with Whisper and writing a timestamped transcript…"
                    : detail.status === "summarizing"
                      ? "The LLM is extracting decisions and action items…"
                      : "Queued — processing starts in a moment."}
                </p>
              </div>
            ) : null}

            {tab === "minutes" && detail.summary ? (
              <div className="section">
                <div className="copy-row">
                  <button className="ghost" onClick={() => copy(minutesText)}>
                    Copy minutes
                  </button>
                </div>
                <p className="overview">{detail.summary.overview}</p>
                <div className="topics">
                  {(detail.summary.topics || []).map((topic) => (
                    <span className="topic" key={topic}>
                      {topic}
                    </span>
                  ))}
                </div>
                <div className="grid-two">
                  <div className="block">
                    <h4>Key decisions</h4>
                    {(detail.summary.key_decisions || []).length === 0 ? (
                      <p className="empty">No explicit decisions were found.</p>
                    ) : (
                      (detail.summary.key_decisions || []).map((item) => (
                        <div className="decision" key={item}>
                          {item}
                        </div>
                      ))
                    )}
                  </div>
                  <div className="block">
                    <h4>Action items</h4>
                    <div className="actions">
                      {(detail.action_items || []).length === 0 ? (
                        <p className="empty">No tasks were assigned in this meeting.</p>
                      ) : (
                        detail.action_items.map((item) => (
                          <label key={item.id} className={`action ${item.done ? "done" : ""}`}>
                            <input
                              type="checkbox"
                              checked={item.done}
                              onChange={() => onToggle(item)}
                            />
                            <div>
                              <div className="task">{item.task}</div>
                              <div className="owner">
                                <span>{item.owner || "Unassigned"}</span>
                                {item.due ? <span>Due {item.due}</span> : null}
                              </div>
                            </div>
                          </label>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {tab === "transcript" && detail.transcript ? (
              <div className="section">
                <div className="copy-row">
                  <button className="ghost" onClick={() => copy(detail.transcript.full_text)}>
                    Copy transcript
                  </button>
                </div>
                {detail.transcript.segments?.length ? (
                  <div className="transcript">
                    {detail.transcript.segments.map((segment, index) => (
                      <div className="segment" key={`${segment.start}-${index}`}>
                        <div className="time">{formatTime(segment.start)}</div>
                        <div>{segment.text}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="plain">{detail.transcript.full_text}</p>
                )}
              </div>
            ) : null}

            {tab === "audio" ? (
              <div className="section">
                <p className="empty">Original recording</p>
                <audio className="player" controls src={api.audioUrl(detail.id)} />
              </div>
            ) : null}

            {detail.status === "completed" && !detail.summary && tab === "minutes" ? (
              <div className="section">
                <p className="empty">Minutes were not generated.</p>
              </div>
            ) : null}
          </section>
        )}

        <input
          ref={inputRef}
          className="file-input"
          type="file"
          accept="audio/*,video/mp4,.m4a,.mp3,.wav,.webm,.ogg,.flac,.mpeg,.mpga"
          onChange={(event) => handleFiles(event.target.files)}
        />
      </main>
    </div>
  );
}
