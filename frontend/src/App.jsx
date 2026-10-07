import { Component, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ThemeProvider } from "./context/ThemeContext";
import { useTheme } from "./hooks/useTheme";

let csrfToken = "";
let csrfRequest = null;

async function loadCsrf() {
  if (csrfToken) return csrfToken;
  if (!csrfRequest) {
    csrfRequest = (async () => {
      const response = await request("/api/csrf", { credentials: "include" });
      const payload = await response.json().catch(() => null);
      if (!response.ok || !payload?.ok || typeof payload.data?.csrfToken !== "string") {
        throw new Error(payload?.error?.message || `Could not connect to the API (${response.status}).`);
      }
      csrfToken = payload.data.csrfToken;
      return csrfToken;
    })();
  }
  try {
    return await csrfRequest;
  } finally {
    csrfRequest = null;
  }
}

async function request(path, options) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 15000);
  try {
    return await fetch(path, { ...options, signal: controller.signal });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("The server took too long to respond. Please try again.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function api(path, { method = "GET", body } = {}) {
  const upperMethod = method.toUpperCase();
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(upperMethod) && !csrfToken) {
    await loadCsrf();
  }

  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(upperMethod)) {
    headers["X-CSRFToken"] = csrfToken;
  }

  const response = await request(path, {
    method: upperMethod,
    credentials: "include",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload?.ok) {
    const error = new Error(payload?.error?.message || `Request failed (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return payload.data;
}

const initialRounds = [1, 2, 3, 4].map((spinNumber) => ({
  spinNumber,
  title: `Round ${spinNumber}`,
  description: "",
}));
const wheelColors = ["#d2fc69", "#a494ff", "#ff9a72", "#69d8dd", "#ffc46b", "#ff82b2", "#72a9ff", "#b8e986"];

export class AppErrorBoundary extends Component {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error("The frontend could not render the application.", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="login-layout">
          <section className="login-card" role="alert">
            <h1>We hit a problem.</h1>
            <p className="muted">The control room could not be displayed. Reload the page to try again.</p>
            <button className="button button-primary" onClick={() => window.location.reload()}>Reload page</button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

function App() {
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [initialError, setInitialError] = useState("");
  const [health, setHealth] = useState("checking");
  const [teamThemeKey, setTeamThemeKey] = useState(null);

  useEffect(() => {
    let active = true;
    const bootstrap = async () => {
      try {
        await loadCsrf();
        const [healthResult, sessionResult] = await Promise.allSettled([
          api("/api/health"),
          api("/api/auth/me"),
        ]);
        if (!active) return;
        if (healthResult.status === "fulfilled") {
          setHealth("online");
        } else {
          setHealth("offline");
          setInitialError(healthResult.reason.message);
        }
        if (sessionResult.status === "fulfilled") {
          setUser(sessionResult.value);
        } else if (sessionResult.reason.status !== 401) {
          setInitialError(sessionResult.reason.message);
        }
      } catch (error) {
        if (active) {
          setHealth("offline");
          setInitialError(error.message);
        }
      } finally {
        if (active) setCheckingSession(false);
      }
    };
    bootstrap();

    return () => {
      active = false;
    };
  }, []);

  const signOut = async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
      setUser(null);
      setTeamThemeKey(null);
    } catch (error) {
      setInitialError(error.message);
    }
  };

  if (checkingSession) {
    return <LoadingScreen label="Connecting to the game server…" />;
  }

  if (!user) {
    return (
      <LoginScreen
        error={initialError}
        health={health}
        onLogin={(nextUser) => {
          setInitialError("");
          setTeamThemeKey(null);
          setUser(nextUser);
        }}
      />
    );
  }

  return (
    <ThemeProvider themeKey={user.role === "team" ? teamThemeKey : null}>
      <AppShell
        user={user}
        health={health}
        onSignOut={signOut}
        onTeamThemeChange={setTeamThemeKey}
      />
    </ThemeProvider>
  );
}

function AppShell({ user, health, onSignOut, onTeamThemeChange }) {
  const { theme } = useTheme();
  return (
    <main className="app-shell" data-theme={theme?.key || "default"} style={theme?.variables}>
      <header className="topbar">
        <a className="brand" href="/" aria-label="4-SPIN home">
          <span className="brand-mark">{theme?.logo || "4"}</span>
          <span>{theme ? theme.name.toUpperCase() : <>SPIN<span className="brand-period">.</span></>}</span>
          <span className="brand-tag">{theme ? "TEAM THEME" : "CONTROL ROOM"}</span>
        </a>
        <div className="topbar-right">
          <span className={`connection ${health}`}>
            <i /> {health === "online" ? "SERVER ONLINE" : "SERVER CHECK"}
          </span>
          <span className="account-chip">
            <span className="avatar">{user.role === "admin" ? "A" : user.role === "volunteer" ? "V" : "T"}</span>
            <span>{user.role === "admin" ? "ADMIN" : user.role === "volunteer" ? `VOLUNTEER · ${user.username}` : user.team?.name || user.username}</span>
          </span>
          <button className="button button-quiet sign-out" onClick={onSignOut}>Sign out</button>
        </div>
      </header>
      {user.role === "admin"
        ? <AdminDashboard />
        : user.role === "volunteer"
          ? <VolunteerDashboard user={user} />
          : <TeamDashboard user={user} onThemeChange={onTeamThemeChange} />}
      <footer className="site-footer">
        <span>4-SPIN COMPETITION SYSTEM</span>
        <span>LIVE COMPETITION <b>•</b> Data is served by your Django API</span>
      </footer>
    </main>
  );
}

function LoadingScreen({ label }) {
  return (
    <main className="login-layout">
      <div className="loading-card"><span className="spinner" />{label}</div>
    </main>
  );
}

function LoginScreen({ error, health, onLogin }) {
  const [role, setRole] = useState("admin");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setFormError("");
    try {
      const data = await api(
        role === "admin"
          ? "/api/auth/admin/login"
          : role === "volunteer"
            ? "/api/auth/volunteer/login"
            : "/api/auth/team/login",
        {
          method: "POST",
          body: role !== "team"
            ? { username: identifier, password }
            : { code: identifier, password },
        },
      );
      onLogin(data);
    } catch (requestError) {
      setFormError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login-layout">
      <div className="login-decoration decoration-one" />
      <div className="login-decoration decoration-two" />
      <section className="login-intro">
        <div className="eyebrow"><span /> THE GAME IS ON</div>
        <h1>Four spins.<br /><em>One champion.</em></h1>
        <p>A live competition control room for the players, the pressure, and the final points.</p>
        <div className="intro-stats">
          <div><strong>04</strong><span>ROUNDS</span></div>
          <div><strong>30</strong><span>TEAMS</span></div>
          <div><strong>01</strong><span>WINNER</span></div>
        </div>
        <div className="orbit orbit-a" /><div className="orbit orbit-b" />
      </section>
      <section className="login-card">
        <div className="card-kicker">WELCOME TO THE ARENA</div>
        <h2>Sign in to play</h2>
        <p className="muted">Choose your access and enter your credentials.</p>
        <div className="role-switch" role="group" aria-label="Account type">
          <button type="button" aria-pressed={role === "admin"} className={role === "admin" ? "active" : ""} onClick={() => { setRole("admin"); setIdentifier(""); }}>
            <span>♙</span> Administrator
          </button>
          <button type="button" aria-pressed={role === "team"} className={role === "team" ? "active" : ""} onClick={() => { setRole("team"); setIdentifier(""); }}>
            <span>♟</span> Team
          </button>
          <button type="button" aria-pressed={role === "volunteer"} className={role === "volunteer" ? "active" : ""} onClick={() => { setRole("volunteer"); setIdentifier(""); }}>
            <span>✓</span> Volunteer
          </button>
        </div>
        <form onSubmit={submit} className="login-form">
          <label htmlFor="identifier">{role === "team" ? "TEAM CODE" : "USERNAME"}</label>
          <input
            id="identifier"
            autoComplete="username"
            placeholder={role === "team" ? "e.g. TEAM01" : role === "volunteer" ? "Enter volunteer username" : "Enter admin username"}
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            required
          />
          <label htmlFor="password">PASSWORD</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            placeholder="Enter your password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          {(formError || error) && <div className="alert alert-error" role="alert">{formError || error}</div>}
          <button className="button button-primary login-submit" disabled={busy}>
            {busy ? "Signing in…" : "Enter control room"} <span>↗</span>
          </button>
        </form>
        <div className="login-status"><span className={`status-dot ${health}`} /> API {health === "online" ? "CONNECTED" : health === "offline" ? "OFFLINE" : "CONNECTING"}</div>
      </section>
    </main>
  );
}

function AdminDashboard() {
  const [competition, setCompetition] = useState(null);
  const [queue, setQueue] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [duration, setDuration] = useState("15");
  const [roundDetails, setRoundDetails] = useState(initialRounds);
  const [setup, setSetup] = useState(null);
  const hasLoadedSetup = useRef(false);
  const [wheelItems, setWheelItems] = useState([]);
  const [newWheelItem, setNewWheelItem] = useState("");
  const [editorThemeKey, setEditorThemeKey] = useState("");
  const [questionThemeKey, setQuestionThemeKey] = useState("");
  const [questionRound, setQuestionRound] = useState(1);
  const [questionText, setQuestionText] = useState("");
  const [questionPoints, setQuestionPoints] = useState("100");
  const [editingQuestionId, setEditingQuestionId] = useState(null);
  const [questionItems, setQuestionItems] = useState([]);
  const [rejectReasons, setRejectReasons] = useState({});
  const [selectedSpin, setSelectedSpin] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [state, pending, scores, wheel, setupData, questionData] = await Promise.all([
        api("/api/competition"),
        api("/api/admin/verifications"),
        api("/api/leaderboard"),
        api("/api/admin/wheel-items"),
        api("/api/admin/competition/setup"),
        api("/api/admin/questions"),
      ]);
      const availableThemes = wheel.items?.length
        ? wheel.items
        : setupData.themes || [];
      setCompetition(state);
      setQueue(pending.items || []);
      setLeaderboard(scores.items || []);
      setWheelItems(wheel.items || []);
      setQuestionItems(questionData.items || []);
      setSetup(setupData);
      if (!hasLoadedSetup.current) {
        setDuration(String(Math.round((setupData.spinDurationSeconds || 900) / 60)));
        hasLoadedSetup.current = true;
      }
      setEditorThemeKey((current) =>
        availableThemes.some((theme) => theme.key === current)
          ? current
          : availableThemes[0]?.key || "",
      );
      setQuestionThemeKey((current) =>
        availableThemes.some((theme) => theme.key === current)
          ? current
          : availableThemes[0]?.key || "",
      );
      setRoundDetails((current) =>
        initialRounds.map((base) => {
          const saved = setupData.rounds?.find((item) => item.spinNumber === base.spinNumber);
          const edited = current.find((item) => item.spinNumber === base.spinNumber);
          return { ...base, ...saved, ...edited };
        }),
      );
      setError("");
    } catch (requestError) {
      setError(requestError.message);
    }
  }, []);

  usePolling(refresh, 4000);

  const remaining = useCountdown(competition);
  const displayRemaining = ["running", "paused"].includes(competition?.status) ? remaining : (setup?.spinDurationSeconds || Number(duration) * 60);
  const started = false; // Intentionally unlocked
  const questionsLocked = ["running", "paused", "starting"].includes(competition?.status);
  const displaySpin = selectedSpin !== null ? selectedSpin : (competition?.currentSpin || 0);
  const canStart = competition && (
    competition.status === "not_started" ||
    (competition.status === "running" && competition.timerExpired) ||
    competition.status === "finished" ||
    selectedSpin !== null
  ) && setup?.ready;

  const runAction = async (key, action, successMessage) => {
    setBusy(key);
    setNotice("");
    setError("");
    try {
      await action();
      setNotice(successMessage);
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy("");
    }
  };

  const startSpin = () => runAction(
    "spin",
    () => api("/api/admin/competition/spin/start", {
      method: "POST",
      body: {},
    }),
    "Round started. Each team can spin once to select its own theme for this round.",
  );

  const startSpecificSpin = (spinNumber) => runAction(
    "spin",
    () => api("/api/admin/competition/spin/start", {
      method: "POST",
      body: { spinNumber },
    }),
    `Round ${spinNumber} started. Each team can spin once to set this round’s shared theme.`,
  );

  const addWheelItem = (event) => {
    event.preventDefault();
    runAction("wheel-item", async () => {
      await api("/api/admin/wheel-items/add", {
        method: "POST",
        body: { name: newWheelItem },
      });
      setNewWheelItem("");
    }, "Wheel item added.");
  };

  const removeWheelItem = (item) => runAction(
    `remove-wheel-${item.key}`,
    () => api(`/api/admin/wheel-items/${encodeURIComponent(item.key)}`, { method: "DELETE" }),
    `${item.name} removed from the wheel.`,
  );

  const saveDuration = (event) => {
    event.preventDefault();
    runAction("duration", () => api("/api/admin/competition/settings", {
      method: "PUT",
      body: { spinDurationSeconds: Number(duration) * 60 },
    }), "Spin duration saved.");
  };

  const saveQuestion = (event) => {
    event.preventDefault();
    return runAction("question-save", async () => {
      const body = {
        question: questionText,
        themeKey: questionThemeKey,
        spinNumber: questionRound,
        points: Number(questionPoints),
      };
      if (editingQuestionId) {
        await api(`/api/admin/questions/${editingQuestionId}`, { method: "PUT", body });
      } else {
        await api("/api/admin/questions", { method: "POST", body });
      }
      setQuestionText("");
      setQuestionPoints("100");
      setEditingQuestionId(null);
    }, editingQuestionId ? "Question updated." : "Question added.");
  };

  const editQuestion = (question) => {
    setQuestionThemeKey(question.themeKey);
    setQuestionRound(question.spinNumber);
    setQuestionText(question.question);
    setQuestionPoints(String(question.points));
    setEditingQuestionId(question.id);
  };

  const deleteQuestion = (question) => {
    if (!window.confirm("Delete this question?")) return;
    runAction(`question-delete-${question.id}`, () => api(`/api/admin/questions/${question.id}/delete`, {
      method: "DELETE",
    }), "Question deleted.");
  };

  const saveRoundDetails = (event, round) => {
    if (event) event.preventDefault();
    return runAction(`round-${round.spinNumber}`, () => api(`/api/admin/rounds/${round.spinNumber}`, {
      method: "PUT",
      body: { title: round.title, description: round.description },
    }), `Round ${round.spinNumber} details saved.`);
  };

  const review = (item, approved) => runAction(`review-${item.id}`, () => api(
    `/api/admin/verifications/${item.id}/${approved ? "approve" : "reject"}`,
    {
      method: "POST",
      ...(approved ? {} : { body: { reason: rejectReasons[item.id] || "Please try again." } }),
    },
  ), approved ? `${item.teamName} approved; the task's configured points were awarded.` : `${item.teamName}'s submission was rejected.`);

  const statusLabel = competition?.status?.replace("_", " ") || "loading";
  return (
    <div className="dashboard">
      <section className="welcome-row">
        <div>
          <div className="eyebrow"><span /> ADMIN CONSOLE</div>
          <h1>Let’s run the <em>game.</em></h1>
          <p>Configure the rounds, keep the clock moving, and call the winner.</p>
        </div>
        <div className="live-badge"><span className="pulse" /> LIVE CONTROL</div>
      </section>

      {(error || notice) && (
        <div className={`alert ${error ? "alert-error" : "alert-success"}`} role={error ? "alert" : "status"}>
          <span>{error ? "!" : "✓"}</span>{error || notice}
          <button onClick={() => { setError(""); setNotice(""); }} aria-label="Dismiss message">×</button>
        </div>
      )}

      <section className="admin-grid">
        <article className="panel control-panel">
          <PanelHeading eyebrow="ROUND CONTROL" title="Spin the wheel" />
          <div className="control-content">
            <SpinWheel items={wheelItems} selectedKey={competition?.theme?.key} />
            <div className="spin-info">
              <div className="spin-index">ROUND <strong>{String(displaySpin).padStart(2, "0")}</strong><span>/ 04</span></div>
              <div className="timer-label">TIME REMAINING</div>
              <div className={`timer ${competition?.timerExpired ? "expired" : ""}`}>{formatTime(displayRemaining)}</div>
              <div className="round-state"><span className={`state-dot ${competition?.status || "loading"}`} />{statusLabel}</div>
              <div className="spin-actions" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <button
                    className="button button-primary"
                    onClick={() => {
                      if (selectedSpin !== null) startSpecificSpin(selectedSpin);
                      else startSpin();
                    }}
                    disabled={!canStart || !!busy}
                  >
                    {busy === "spin" ? "Starting…" : selectedSpin ? `Start round ${selectedSpin}` : competition?.currentSpin ? "Start next round" : "Start first round"}
                  </button>
                  {competition?.status === "running" && (
                    <button className="button button-outline" disabled={!!busy} onClick={() => runAction("pause", () => api("/api/admin/competition/pause", { method: "POST" }), "Competition paused.")}>Pause</button>
                  )}
                  {competition?.status === "paused" && (
                    <button className="button button-outline" disabled={!!busy} onClick={() => runAction("resume", () => api("/api/admin/competition/resume", { method: "POST" }), "Competition resumed.")}>Resume</button>
                  )}
                </div>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {competition?.status === "running" && !competition.timerExpired && (
                    <button className="button button-warning" style={{ background: '#ffc46b', color: '#111827', border: 'none' }} disabled={!!busy} onClick={() => runAction("expire", () => api("/api/admin/competition/spin/expire", { method: "POST" }), "Round timer ended early.")}>End Timer</button>
                  )}
                  {["running", "paused"].includes(competition?.status) && (
                    <button className="button button-danger" disabled={!!busy} onClick={() => {
                      if (window.confirm("Finish the competition now?")) {
                        runAction("finish", () => api("/api/admin/competition/finish", { method: "POST" }), "Competition finished.");
                      }
                    }}>Finish</button>
                  )}
                </div>
              </div>
              {competition?.status === "running" && !competition.timerExpired && (
                <p className="hint">The next round unlocks when this timer expires.</p>
              )}
              {competition?.status === "running" && competition.timerExpired && (
                <p className="hint warning-text">Time is up. You can start the next round.</p>
              )}
              {!setup?.ready && (
                <section className="start-checklist" aria-label="Round start requirements">
                  <div className="checklist-title">START REQUIREMENTS</div>
                  <SetupCheck
                    complete={Boolean(setup?.spinDurationSeconds)}
                    label={setup?.spinDurationSeconds
                      ? `Round duration saved · ${formatTime(setup.spinDurationSeconds)}`
                      : "Save a round duration"}
                  />
                  <SetupCheck
                    complete={(setup?.configuredSpins?.length || 0) === 4}
                    label={`Questions ready · ${setup?.configuredSpins?.length || 0}/4`}
                  />
                  <SetupCheck
                    complete={(setup?.configuredRounds?.length || 0) === 4}
                    label={`Round titles and descriptions · ${setup?.configuredRounds?.length || 0}/4`}
                  />
                  <SetupCheck
                    complete={(setup?.activeTeamCount || 0) > 0}
                    label={`Active teams · ${setup?.activeTeamCount ?? "—"}${setup?.activeTeamCount === 1 ? " team" : " teams"}${setup?.activeTeamCount ? "" : " · at least 1 required"}`}
                  />
                  <SetupCheck
                    complete={(setup?.wheelItemCount || 0) > 0}
                    label={`Wheel items · ${setup?.wheelItemCount ?? "—"}`}
                  />
                </section>
              )}
            </div>
          </div>
          {(() => {
            const round = roundDetails.find((item) => item.spinNumber === displaySpin);
            const selectedTask = round ? { ...round, themeName: "ROUND" } : null;
            return selectedTask ? (
              <div className="selected-task-preview" style={{ padding: '0 30px 25px 30px', borderTop: '1px solid rgba(202, 214, 244, 0.05)', paddingTop: '20px' }}>
                <div style={{ color: 'var(--lime)', font: '600 24px var(--display)', letterSpacing: '2px', textTransform: 'uppercase', marginBottom: '12px' }}>{selectedTask.themeName} · {selectedTask.title || `Round ${selectedTask.spinNumber} Task`}</div>
                <p style={{ margin: '0', color: '#e7eaf2', fontSize: '16px', lineHeight: '1.7' }}>{selectedTask.description || "No description provided."}</p>
              </div>
            ) : null;
          })()}
        </article>

        <article className="panel setup-panel">
          <PanelHeading eyebrow="BEFORE THE FIRST SPIN" title="Game setup" />
          <form className="duration-form" onSubmit={saveDuration}>
            <label htmlFor="duration">ROUND DURATION <span>MINUTES · 1–1440</span></label>
            <div className="inline-form">
              <input id="duration" type="number" min="1" max="1440" value={duration} disabled={started} onChange={(event) => setDuration(event.target.value)} required />
              <button className="button button-outline" disabled={started || !!busy}>Save</button>
            </div>
          </form>
          <section className="wheel-items-section">
            <div className="task-heading wheel-items-heading">
              <span>WHEEL ITEMS · THEMES</span>
              <small>{`${wheelItems.length} on wheel`}</small>
            </div>
            <form className="wheel-item-form" onSubmit={addWheelItem}>
              <input
                aria-label="New wheel item name"
                placeholder="Add a theme, e.g. Space"
                value={newWheelItem}
                disabled={started || !!busy}
                onChange={(event) => setNewWheelItem(event.target.value)}
                maxLength={100}
                required
              />
              <button className="button button-outline" disabled={started || !!busy}>Add item</button>
            </form>
            <div className="wheel-item-list">
              {wheelItems.map((item, index) => (
                <div className="wheel-item-chip" key={item.key}>
                  <span className="wheel-item-swatch" style={{ background: wheelColors[index % wheelColors.length] }} />
                  <span title={item.name}>{item.name}</span>
                  <button
                    type="button"
                    aria-label={`Remove ${item.name} from the wheel`}
                    title={`Remove ${item.name}`}
                    disabled={!!busy}
                    onClick={() => removeWheelItem(item)}
                  >×</button>
                </div>
              ))}
              {!wheelItems.length && <p className="wheel-empty">Add at least one item before starting a spin.</p>}
            </div>
          </section>
          <div className="task-heading"><span>ROUND TITLE &amp; DESCRIPTION</span><small>{`${setup?.configuredRounds?.length || 0}/4 rounds saved`}</small></div>
          <div className="task-list round-details-list">
            {roundDetails.map((round) => (
              <form className="round-details-row" key={round.spinNumber} onSubmit={(event) => saveRoundDetails(event, round)}>
                <span className={`task-number task-color-${round.spinNumber}`}>{String(round.spinNumber).padStart(2, "0")}</span>
                <div className="task-fields">
                  <input
                    aria-label={`Round ${round.spinNumber} title`}
                    placeholder={`Round ${round.spinNumber} title`}
                    value={round.title}
                    onChange={(event) => setRoundDetails((all) => all.map((item) => item.spinNumber === round.spinNumber ? { ...item, title: event.target.value } : item))}
                    maxLength={100}
                    required
                  />
                  <textarea
                    aria-label={`Round ${round.spinNumber} description`}
                    placeholder="Description shown to teams when this round starts"
                    value={round.description}
                    onChange={(event) => setRoundDetails((all) => all.map((item) => item.spinNumber === round.spinNumber ? { ...item, description: event.target.value } : item))}
                    maxLength={2000}
                    required
                    rows={3}
                  />
                  <div className="round-details-actions">
                    <button className="button button-outline" disabled={!!busy}>Save round details</button>
                    <span className={`task-save-status ${(setup?.configuredRounds || []).includes(round.spinNumber) ? "saved" : ""}`}>
                      {(setup?.configuredRounds || []).includes(round.spinNumber) ? "✓ Saved" : "Not saved"}
                    </span>
                  </div>
                </div>
              </form>
            ))}
          </div>
          {false && (<>
          <div className="task-heading"><span>THEME SPECIFIC QUESTIONS</span><small>{`${setup?.configuredSpins?.length || 0}/4 rounds complete`}</small></div>
          <form className="question-entry-form question-entry-form-inline" onSubmit={saveQuestion}>
            <div className="question-manager-controls">
              <label className="question-round-filter">THEME
                <select aria-label="Question theme" value={questionThemeKey} onChange={(event) => setQuestionThemeKey(event.target.value)}>
                  {wheelItems.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}
                </select>
              </label>
              <label className="question-round-filter">ROUND
                <select aria-label="Question round" value={questionRound} onChange={(event) => setQuestionRound(Number(event.target.value))}>
                  {[1, 2, 3, 4].map((round) => <option key={round} value={round}>Round {round}</option>)}
                </select>
              </label>
            </div>
            <label htmlFor="question-entry-inline">{editingQuestionId ? "EDIT QUESTION" : "ADD QUESTION"}</label>
            <textarea id="question-entry-inline" aria-label="Question text" placeholder="Write a question for the selected theme and round" value={questionText} onChange={(event) => setQuestionText(event.target.value)} maxLength={1000} rows={3} required />
            <div className="question-entry-actions">
              <label>POINTS <input type="number" min="1" max="100000" value={questionPoints} onChange={(event) => setQuestionPoints(event.target.value)} required /></label>
              <button className="button button-primary" disabled={!questionThemeKey || !!busy || (questionsLocked && Boolean(editingQuestionId))}>{editingQuestionId ? "Save changes" : "+ Add Question"}</button>
            </div>
          </form>
          <label className="task-theme-picker">
            QUESTION THEME
            <select
              aria-label="Question theme"
              value={editorThemeKey}
              disabled={started || !!busy || !wheelItems.length}
              onChange={(event) => setEditorThemeKey(event.target.value)}
            >
              {wheelItems.map((theme) => <option key={theme.key} value={theme.key}>{theme.name}</option>)}
            </select>
          </label>
          <div className="task-list">
            {tasks.filter((item) => item.themeKey === editorThemeKey).map((task) => (
              <form className="task-row" key={`${task.themeKey}-${task.spinNumber}`} onSubmit={(event) => saveTask(event, task)} onClick={() => setSelectedSpin(task.spinNumber)}>
                <span className={`task-number task-color-${task.spinNumber}`} style={{ cursor: "pointer" }} title={`Select Round ${task.spinNumber}`}>{String(task.spinNumber).padStart(2, "0")}</span>
                <div className="task-fields" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <input
                    aria-label={`Round ${task.spinNumber} question title`}
                    placeholder={`Round ${task.spinNumber} task title`}
                    value={task.title}
                    disabled={started}
                    onChange={(event) => setTasks((all) => all.map((item) => item.spinNumber === task.spinNumber && item.themeKey === task.themeKey ? { ...item, title: event.target.value } : item))}
                    required
                    style={{ fontSize: '14px', padding: '10px' }}
                  />
                  <textarea
                    aria-label={`Round ${task.spinNumber} description`}
                    placeholder="Short task description"
                    value={task.description}
                    disabled={started}
                    onChange={(event) => setTasks((all) => all.map((item) => item.spinNumber === task.spinNumber && item.themeKey === task.themeKey ? { ...item, description: event.target.value } : item))}
                    required
                    style={{ 
                      minWidth: 0, border: '1px solid rgba(187,201,233,.13)', borderRadius: '6px', 
                      outline: 'none', color: '#eff1f8', background: 'rgba(4,9,20,.3)', width: '100%', 
                      padding: '10px', fontSize: '14px', resize: 'vertical', minHeight: '120px', 
                      fontFamily: 'inherit', display: 'block'
                    }}
                  />
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '14px', color: '#9ba6bb', fontWeight: 500, letterSpacing: '0.5px' }}>Points</span>
                    <input
                      aria-label={`Round ${task.spinNumber} points`}
                      className="points-input"
                      type="number"
                      min="1"
                      max="100000"
                      placeholder="PTS"
                      value={task.points}
                      disabled={started}
                      onChange={(event) => setTasks((all) => all.map((item) => item.spinNumber === task.spinNumber && item.themeKey === task.themeKey ? { ...item, points: event.target.value } : item))}
                      required
                      style={{ width: '100px', fontSize: '14px', padding: '10px', textAlign: 'center' }}
                    />
                  </div>
                  <button className="save-task" type="button" title={`Save ${task.themeName} question for round ${task.spinNumber}`} disabled={started || !!busy} onClick={(e) => saveTask(e, task)}>↗</button>
                  <span className={`task-save-status ${setup?.tasks?.some((item) => item.spinNumber === task.spinNumber && item.themeKey === task.themeKey) ? "saved" : ""}`}>
                    {setup?.tasks?.some((item) => item.spinNumber === task.spinNumber && item.themeKey === task.themeKey) ? "✓ Saved" : "Not saved"}
                  </span>
                  <button
                    type="button"
                    className="button button-outline"
                    style={{ padding: '8px 24px', fontSize: '14px', whiteSpace: 'nowrap', width: 'fit-content' }}
                    title={`Select round ${task.spinNumber}`}
                    disabled={!!busy}
                    onClick={(event) => { event.preventDefault(); event.stopPropagation(); setSelectedSpin(task.spinNumber); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                  >
                    Select round
                  </button>
                </div>
              </form>
            ))}
          </div>
          <p className="setup-note">Add at least one question for every theme in every round. Teams only receive questions for their assigned theme.</p>
          </>)}
        </article>
      </section>

      <section className="panel question-management-panel">
        <PanelHeading
          eyebrow="ADMIN QUESTION LIBRARY"
          title="Manage Questions"
          right={<span className="count-pill">{questionItems.length} QUESTIONS</span>}
        />
        <div className="question-manager-controls">
          <label className="question-round-filter">
            THEME
            <select
              aria-label="Filter questions by theme"
              value={questionThemeKey}
              onChange={(event) => { setQuestionThemeKey(event.target.value); setEditingQuestionId(null); setQuestionText(""); }}
            >
              {wheelItems.map((theme) => <option key={theme.key} value={theme.key}>{theme.name}</option>)}
            </select>
          </label>
          <label className="question-round-filter">
            ROUND
            <select value={questionRound} onChange={(event) => { setQuestionRound(Number(event.target.value)); setEditingQuestionId(null); setQuestionText(""); }}>
              {[1, 2, 3, 4].map((round) => <option value={round} key={round}>Round {round}</option>)}
            </select>
          </label>
        </div>
        <form className="question-entry-form" onSubmit={saveQuestion}>
          <label htmlFor="question-entry">{editingQuestionId ? "EDIT QUESTION" : "ADD QUESTION"}</label>
          <textarea
            id="question-entry"
            aria-label="Question text"
            placeholder="Write a question for the selected theme and round"
            value={questionText}
            onChange={(event) => setQuestionText(event.target.value)}
            maxLength={1000}
            rows={3}
            required
          />
          <div className="question-entry-actions">
            <label>
              POINTS
              <input type="number" min="1" max="100000" value={questionPoints} onChange={(event) => setQuestionPoints(event.target.value)} required />
            </label>
            <button className="button button-primary" disabled={!questionThemeKey || !!busy || (questionsLocked && Boolean(editingQuestionId))}>
              {editingQuestionId ? "Save changes" : "+ Add Question"}
            </button>
            {editingQuestionId && (
              <button type="button" className="button button-outline" onClick={() => { setEditingQuestionId(null); setQuestionText(""); setQuestionPoints("100"); }}>
                Cancel
              </button>
            )}
          </div>
          {!questionThemeKey && <p className="setup-note">Add a wheel theme before creating questions.</p>}
          {questionsLocked && <p className="setup-note">You can add questions during a round. Editing and deleting questions is locked while a round is active.</p>}
        </form>
        <div className="question-library-list">
          <div className="task-heading">
            <span>{wheelItems.find((theme) => theme.key === questionThemeKey)?.name || "Theme"} QUESTIONS</span>
            <small>ROUND {questionRound}</small>
          </div>
          {questionItems.filter((item) => item.themeKey === questionThemeKey && item.spinNumber === questionRound).length ? (
            questionItems
              .filter((item) => item.themeKey === questionThemeKey && item.spinNumber === questionRound)
              .map((question, index) => (
                <article className="question-library-item" key={question.id}>
                  <span className="question-number">{String(index + 1).padStart(2, "0")}</span>
                  <p>{question.question}</p>
                  <span className="question-points">{question.points} PTS</span>
                  <div className="question-item-actions">
                    <button type="button" className="button button-outline" disabled={questionsLocked || !!busy} onClick={() => editQuestion(question)}>Edit</button>
                    <button type="button" className="button button-danger" disabled={questionsLocked || !!busy} onClick={() => deleteQuestion(question)}>Delete</button>
                  </div>
                </article>
              ))
          ) : (
            <p className="question-empty">No questions for this theme and round yet.</p>
          )}
        </div>
      </section>

      <section className="lower-grid">
        <article className="panel queue-panel">
          <PanelHeading eyebrow="NEEDS YOUR CALL" title="Verification queue" right={<span className="count-pill">{queue.length} PENDING</span>} />
          {queue.length === 0 ? (
            <EmptyState icon="✓" title="All clear" text="New team submissions will appear here." />
          ) : (
            <div className="queue-list">
              {queue.map((item) => (
                <div className="queue-item" key={item.id}>
                  <div className="queue-position">{String(item.queuePosition).padStart(2, "0")}</div>
                  <div className="queue-details">
                    <strong>{item.teamName}</strong>
                    <span>Spin {item.spinNumber} <b>·</b> {item.taskTitle}</span>
                  </div>
                  <div className="review-controls">
                    <input
                      aria-label={`Rejection reason for ${item.teamName}`}
                      placeholder="Reason if rejecting"
                      value={rejectReasons[item.id] || ""}
                      onChange={(event) => setRejectReasons((all) => ({ ...all, [item.id]: event.target.value }))}
                    />
                    <button className="review-reject" disabled={!!busy} onClick={() => review(item, false)}>Reject</button>
                    <button className="review-approve" disabled={!!busy} onClick={() => review(item, true)}>Approve</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="panel leaderboard-panel">
          <PanelHeading eyebrow="THE SCOREBOARD" title="Leaderboard" right={<button className="text-button" onClick={refresh}>Refresh ↻</button>} />
          <Leaderboard rows={leaderboard.slice(0, 8)} />
        </article>
      </section>
      <VolunteerAccountPanel />
    </div>
  );
}

function VolunteerAccountPanel() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const createAccount = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const volunteer = await api("/api/admin/volunteers", {
        method: "POST",
        body: { username, password },
      });
      setNotice(`Volunteer account “${volunteer.username}” created.`);
      setUsername("");
      setPassword("");
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="panel volunteer-account-panel">
      <PanelHeading eyebrow="ACCESS MANAGEMENT" title="Create volunteer account" />
      <form className="volunteer-account-form" onSubmit={createAccount}>
        <label>
          USERNAME
          <input value={username} onChange={(event) => setUsername(event.target.value)} maxLength={80} autoComplete="off" required />
        </label>
        <label>
          TEMPORARY PASSWORD
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} maxLength={1024} autoComplete="new-password" required />
        </label>
        <button className="button button-outline" disabled={busy}>{busy ? "Creating…" : "Create volunteer"}</button>
      </form>
      <p className="setup-note">Volunteers can review submissions and mark team attendance for each round. Passwords must be at least 12 characters.</p>
      {(error || notice) && <div className={`alert ${error ? "alert-error" : "alert-success"}`}>{error || notice}</div>}
    </article>
  );
}

function VolunteerDashboard({ user }) {
  const [section, setSection] = useState("verifications");
  const [queue, setQueue] = useState([]);
  const [attendance, setAttendance] = useState([]);
  const [spinNumber, setSpinNumber] = useState(1);
  const [counts, setCounts] = useState({ presentCount: 0, absentCount: 0, unmarkedCount: 0 });
  const [rejectReasons, setRejectReasons] = useState({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");

  const refresh = useCallback(async () => {
    try {
      const queueResult = await api("/api/admin/verifications");
      setQueue(queueResult.items || []);
      if (section === "attendance") {
        const result = await api(`/api/volunteer/attendance?spinNumber=${spinNumber}`);
        setAttendance(result.items || []);
        setCounts({
          presentCount: result.presentCount,
          absentCount: result.absentCount,
          unmarkedCount: result.unmarkedCount,
        });
      }
      setError("");
    } catch (requestError) {
      setError(requestError.message);
    }
  }, [section, spinNumber]);

  usePolling(refresh, 5000);

  const review = async (item, approved) => {
    setBusy(`review-${item.id}`);
    setError("");
    setNotice("");
    try {
      await api(`/api/admin/verifications/${item.id}/${approved ? "approve" : "reject"}`, {
        method: "POST",
        ...(approved ? {} : { body: { reason: rejectReasons[item.id] || "Please try again." } }),
      });
      setNotice(approved
        ? `${item.teamName} approved; the task's configured points were awarded.`
        : `${item.teamName}'s submission was rejected.`);
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy("");
    }
  };

  const markAttendance = async (item, status) => {
    const key = `attendance-${item.teamId}`;
    setBusy(key);
    setError("");
    setNotice("");
    try {
      await api(`/api/volunteer/attendance/${spinNumber}/${encodeURIComponent(item.teamId)}`, {
        method: "PUT",
        body: { status },
      });
      setNotice(`${item.teamName} marked ${status} for round ${spinNumber}.`);
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="dashboard volunteer-dashboard">
      <section className="welcome-row">
        <div>
          <div className="eyebrow"><span /> VOLUNTEER DESK</div>
          <h1>Here to help, <em>{user.username}.</em></h1>
          <p>Review team submissions and record attendance one round at a time.</p>
        </div>
        <div className="live-badge"><span className="pulse" /> VOLUNTEER ACCESS</div>
      </section>
      {(error || notice) && (
        <div className={`alert ${error ? "alert-error" : "alert-success"}`} role={error ? "alert" : "status"}>
          <span>{error ? "!" : "✓"}</span>{error || notice}
          <button onClick={() => { setError(""); setNotice(""); }} aria-label="Dismiss message">×</button>
        </div>
      )}
      <nav className="volunteer-tabs" aria-label="Volunteer tools">
        <button type="button" aria-pressed={section === "verifications"} className={section === "verifications" ? "active" : ""} onClick={() => setSection("verifications")}>
          Verification queue <span>{queue.length}</span>
        </button>
        <button type="button" aria-pressed={section === "attendance"} className={section === "attendance" ? "active" : ""} onClick={() => setSection("attendance")}>
          Team attendance
        </button>
      </nav>
      {section === "verifications" ? (
        <article className="panel queue-panel volunteer-queue-panel">
          <PanelHeading eyebrow="SUBMISSIONS" title="Verification queue" right={<span className="count-pill">{queue.length} PENDING</span>} />
          {queue.length === 0 ? (
            <EmptyState icon="✓" title="All clear" text="New team submissions will appear here." />
          ) : (
            <div className="queue-list">
              {queue.map((item) => (
                <div className="queue-item" key={item.id}>
                  <div className="queue-position">{String(item.queuePosition).padStart(2, "0")}</div>
                  <div className="queue-details">
                    <strong>{item.teamName}</strong>
                    <span>Round {item.spinNumber} <b>·</b> {item.taskTitle}</span>
                  </div>
                  <div className="review-controls">
                    <input
                      aria-label={`Rejection reason for ${item.teamName}`}
                      placeholder="Reason if rejecting"
                      value={rejectReasons[item.id] || ""}
                      onChange={(event) => setRejectReasons((all) => ({ ...all, [item.id]: event.target.value }))}
                    />
                    <button className="review-reject" disabled={!!busy} onClick={() => review(item, false)}>Reject</button>
                    <button className="review-approve" disabled={!!busy} onClick={() => review(item, true)}>Approve</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>
      ) : (
        <article className="panel attendance-panel">
          <PanelHeading
            eyebrow="ROUND-BY-ROUND ROSTER"
            title="Team attendance"
            right={(
              <label className="round-picker">
                ROUND
                <select value={spinNumber} onChange={(event) => setSpinNumber(Number(event.target.value))}>
                  {[1, 2, 3, 4].map((round) => <option value={round} key={round}>Round {round}</option>)}
                </select>
              </label>
            )}
          />
          <div className="attendance-summary">
            <span><strong>{counts.presentCount}</strong> PRESENT</span>
            <span><strong>{counts.absentCount}</strong> ABSENT</span>
            <span><strong>{counts.unmarkedCount}</strong> UNMARKED</span>
          </div>
          {attendance.length === 0 ? (
            <EmptyState icon="◎" title="No active teams" text="Active teams will appear here for attendance." />
          ) : (
            <div className="attendance-list">
              {attendance.map((item) => (
                <div className="attendance-row" key={item.teamId}>
                  <div className="attendance-team">
                    <strong>{item.teamName}</strong>
                    <span>{item.teamCode}</span>
                  </div>
                  <span className={`attendance-status ${item.status}`}>{item.status}</span>
                  <div className="attendance-actions">
                    <button className={`attendance-present ${item.status === "present" ? "selected" : ""}`} disabled={!!busy} onClick={() => markAttendance(item, "present")}>Present</button>
                    <button className={`attendance-absent ${item.status === "absent" ? "selected" : ""}`} disabled={!!busy} onClick={() => markAttendance(item, "absent")}>Absent</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>
      )}
    </div>
  );
}

function TeamDashboard({ user, onThemeChange }) {
  const { theme } = useTheme();
  const [snapshot, setSnapshot] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [teamWheelRotation, setTeamWheelRotation] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const [teamData, scores] = await Promise.all([
        api("/api/team/assignment"),
        api("/api/leaderboard"),
      ]);
      const themeQuery = teamData.assignment?.theme
        ? `?theme=${encodeURIComponent(teamData.assignment.theme.key)}&round=${teamData.competition?.currentSpin || 0}`
        : "";
      const questionData = await api(`/api/questions${themeQuery}`);
      setSnapshot({ ...teamData, questionItems: questionData.items || [] });
      onThemeChange(teamData.assignment?.theme?.key || null);
      setLeaderboard(scores.items || []);
      setError("");
    } catch (requestError) {
      setError(requestError.message);
    }
  }, [onThemeChange]);

  usePolling(refresh, 4000);

  const competition = snapshot?.competition;
  const assignment = snapshot?.assignment;
  const roundDetails = snapshot?.round;
  const questionItems = snapshot?.questionItems || [];
  const remaining = useCountdown(competition);
  const myRank = useMemo(
    () => leaderboard.find((entry) => entry.teamId === user.team?.id),
    [leaderboard, user.team?.id],
  );
  const assignedTheme = assignment?.theme;
  const teamWheelItems = assignedTheme ? questionItems : competition?.wheelItems || [];
  const completedTasks = Math.min(4, myRank?.completedTasks || 0);
  const progressPercent = Math.round((completedTasks / 4) * 100);
  const canSubmit = competition?.status === "running" && !assignment?.completed &&
    assignment?.verificationStatus !== "waiting" && remaining > 0;
  const canSpin = competition?.status === "running" &&
    !assignment?.spinAttempted &&
    Boolean(assignment) &&
    teamWheelItems.length > 0 &&
    remaining > 0;

  const spinTeamWheel = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api("/api/team/competition/spin", { method: "POST" });
      const selectedKey = assignedTheme ? result.questionId : result.theme.key;
      const items = teamWheelItems;
      const selectedIndex = items.findIndex((item) => item.key === selectedKey);
      if (selectedIndex >= 0) {
        const center = (selectedIndex + 0.5) * (360 / items.length);
        setTeamWheelRotation((current) => {
          const offset = (360 - center - (current % 360) + 360) % 360;
          return current + 1440 + offset;
        });
      }
      await new Promise((resolve) => window.setTimeout(resolve, 2500));
      setNotice(assignedTheme
        ? `Your team received a ${result.theme.name} question.`
        : `Your team is assigned ${result.theme.name} for the remaining rounds.`);
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const submitBuzzer = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api("/api/team/buzzer", { method: "POST" });
      setNotice(`Buzzer registered — you are #${result.queuePosition} in the review queue.`);
      await refresh();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dashboard team-dashboard">
      <section className="welcome-row">
        <div>
          <div className="eyebrow"><span /> {theme ? `${theme.name.toUpperCase()} · TEAM PLAYER` : "TEAM PLAYER"}</div>
          <h1>Ready, <em>{user.team?.name || user.username}?</em></h1>
          <p>{assignedTheme
            ? `Your ${assignedTheme.name} challenge is live. Beat the clock and buzz in when you’re done.`
            : "Your challenge is live here. Beat the clock and buzz in when you’re done."}</p>
        </div>
        <div className="team-score">
          <span>YOUR SCORE</span>
          <strong>{myRank?.points || 0}<small> pts</small></strong>
          <span>{myRank ? `RANK #${myRank.rank}` : "NOT RANKED YET"}</span>
        </div>
      </section>
      <section className="team-overview panel" aria-label="Team progress">
        <div className="team-identity">
          <span>TEAM ID</span>
          <strong>{user.team?.code || user.team?.id || user.username}</strong>
          <span>ASSIGNED THEME</span>
          <strong className="assigned-theme-name">{assignedTheme?.name || "Not selected yet"}</strong>
        </div>
        <div className="team-progress">
          <div className="team-progress-heading">
            <span>CHALLENGE PROGRESS</span>
            <strong>{completedTasks}/4 complete</strong>
          </div>
          <div
            className="team-progress-track"
            role="progressbar"
            aria-label="Completed challenges"
            aria-valuemin="0"
            aria-valuemax="4"
            aria-valuenow={completedTasks}
          >
            <span style={{ width: `${progressPercent}%` }} />
          </div>
          <span className="team-progress-remaining">{4 - completedTasks} challenges remaining</span>
        </div>
      </section>
      {(error || notice) && <div className={`alert ${error ? "alert-error" : "alert-success"}`} role={error ? "alert" : "status"}><span>{error ? "!" : "✓"}</span>{error || notice}</div>}
      {roundDetails && (
        <section className="round-brief panel" aria-label={`Round ${roundDetails.spinNumber} details`}>
          <div className="eyebrow"><span /> ROUND {String(roundDetails.spinNumber).padStart(2, "0")} BRIEF</div>
          <h2>{roundDetails.title}</h2>
          <p>{roundDetails.description}</p>
        </section>
      )}
      <section className="team-grid">
        <article className="panel team-challenge">
          <PanelHeading eyebrow={`ROUND ${String(competition?.currentSpin || 0).padStart(2, "0")} / 04`} title={assignment?.task?.title || "Your challenge"} />
          {assignment?.task ? (
            <>
              <p className="challenge-description">{assignment.task.description}</p>
              <div className="challenge-meta">
                <span><b>✦</b> {assignment.task.points} POINTS</span>
                {assignment.theme && <span><b>◈</b> THEME: {assignment.theme.name}</span>}
              </div>
              <div className="team-timer">
                <div><span>TIME LEFT</span><strong>{formatTime(remaining)}</strong></div>
                <span className={`state-pill ${competition.status}`}>{competition.status}</span>
              </div>
              {assignment.completed ? (
                <div className="submission-state approved"><span>✓</span> Challenge approved — nice work!</div>
              ) : assignment.verificationStatus === "waiting" ? (
                <div className="submission-state waiting"><span>◷</span> Waiting for an administrator to review your buzzer.</div>
              ) : assignment.verificationStatus === "rejected" ? (
                <>
                  <div className="submission-state rejected"><span>!</span> Not approved: {assignment.rejectionReason}.</div>
                  <button className="button button-primary buzzer-button" disabled={!canSubmit || busy} onClick={submitBuzzer}>
                    {busy ? "Sending..." : "Try again"}
                  </button>
                </>
              ) : (
                <button className="button button-primary buzzer-button" disabled={!canSubmit || busy} onClick={submitBuzzer}>
                  {busy ? "Sending buzzer…" : "I completed the challenge"} <span>↗</span>
                </button>
              )}
              {!canSubmit && !assignment.completed && assignment.verificationStatus !== "waiting" && (
                <p className="hint">The buzzer is available while a round is running.</p>
              )}
            </>
          ) : (
            <EmptyState icon="◎" title="Waiting for the next spin" text="Your assigned challenge will show up here once the admin starts the game." />
          )}
        </article>
        <article className="panel team-round-panel">
          <PanelHeading eyebrow="LIVE SPIN" title="Spin wheel" />
          <div className="team-wheel-wrap">
            <SpinWheel
              items={teamWheelItems}
              selectedKey={assignedTheme ? assignment?.task?.id : undefined}
              rotation={teamWheelRotation}
              compact
            />
          </div>
          {assignment?.theme && (
            <div className="team-winning-theme">
              <span>THIS ROUND’S ASSIGNED THEME</span>
              <strong>{assignment.theme.name}</strong>
            </div>
          )}
          <div className="arena-number">{String(competition?.currentSpin || 0).padStart(2, "0")}<span>/04</span></div>
          <div className="arena-label">CURRENT ROUND</div>
          <div className="team-wheel-control">
            {assignment?.spinAttempted ? (
              <div className="submission-state waiting team-spin-state">
                <span>✓</span> Your spin for this round is used.
              </div>
            ) : (
              <>
                <button
                  className="button button-primary team-spin-button"
                  disabled={!canSpin || busy}
                  onClick={spinTeamWheel}
                >
                  {busy ? "Spinning…" : "Spin for a question"} <span>↗</span>
                </button>
                {!canSpin && (
                  <p className="hint team-spin-hint">
                    {competition?.status !== "running"
                      ? "The admin must start a round before you can spin."
                      : !assignment
                        ? "Waiting for your team’s round assignment."
                        : !teamWheelItems.length
                          ? assignedTheme ? "No questions are available for your theme in this round." : "There are no themes on the wheel yet."
                          : remaining <= 0
                            ? "The round timer has expired."
                            : "Your team’s spin is not available right now."}
                  </p>
                )}
              </>
            )}
          </div>
          <div className="arena-rule" />
          <div className="arena-status-row"><span className="state-dot state-dot-inline" />{competition?.status || "Loading status"}</div>
          <p className="muted">This panel refreshes automatically while the game is running.</p>
        </article>
      </section>
      <article className="panel team-leaderboard">
        <PanelHeading eyebrow="SEE WHERE YOU STAND" title="Leaderboard" right={<button className="text-button" onClick={refresh}>Refresh ↻</button>} />
        <Leaderboard rows={leaderboard.slice(0, 10)} currentTeamId={user.team?.id} />
      </article>
    </div>
  );
}

function SpinWheel({ items, rotation = 0, selectedKey, compact = false }) {
  const selectedItem = items.find((item) => item.key === selectedKey);
  const segments = items.length
    ? `conic-gradient(${items.map((item, index) => {
      const size = 360 / items.length;
      return `${wheelColors[index % wheelColors.length]} ${index * size}deg ${(index + 1) * size}deg`;
    }).join(", ")})`
    : undefined;

  return (
    <div className={`wheel-stage ${compact ? "wheel-stage-compact" : ""}`}>
      <div className="wheel-pointer" />
      <div
        className={`wheel ${compact ? "wheel-compact" : ""}`}
        style={{
          transform: `rotate(${rotation}deg)`,
          background: segments,
        }}
      >
        <div className="wheel-center">
          <span>{selectedItem?.name || items.length}</span>
          <small>{selectedItem ? "SELECTED" : items.length ? "THEMES" : "NO ITEMS"}</small>
        </div>
        {items.map((item, index) => {
          const angle = (index + 0.5) * (360 / items.length);
          return (
            <span
              className={`wheel-label ${item.key === selectedKey ? "wheel-label-selected" : ""}`}
              key={item.key}
              style={{
                transform: `rotate(${angle}deg) translateY(${compact ? "-61px" : "-72px"}) rotate(${-angle}deg) translate(-50%, -50%)`,
              }}
              title={item.name}
            >
              {item.name}
            </span>
          );
        })}
      </div>
    </div>
  );
}

function PanelHeading({ eyebrow, title, right }) {
  return (
    <div className="panel-heading">
      <div><div className="panel-eyebrow">{eyebrow}</div><h2>{title}</h2></div>
      {right}
    </div>
  );
}

function SetupCheck({ complete, label }) {
  return (
    <div className={`setup-check ${complete ? "complete" : ""}`}>
      <span>{complete ? "✓" : "!"}</span>
      {label}
    </div>
  );
}

function Leaderboard({ rows, currentTeamId }) {
  if (!rows.length) return <EmptyState icon="↗" title="No scores yet" text="Approved submissions will appear on the board." />;
  return (
    <div className="leaderboard-table">
      <div className="leaderboard-head"><span>RANK</span><span>TEAM</span><span>DONE</span><span>POINTS</span></div>
      {rows.map((row) => (
        <div className={`leaderboard-row ${row.teamId === currentTeamId ? "my-team" : ""}`} key={row.teamId}>
          <span className={`rank rank-${row.rank}`}>{String(row.rank).padStart(2, "0")}</span>
          <strong>{row.teamName}{row.teamId === currentTeamId && <small> YOU</small>}</strong>
          <span className="tasks-done">{row.completedTasks}</span>
          <strong className="score-points">{row.points}<small> pts</small></strong>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ icon, title, text }) {
  return <div className="empty-state"><span className="empty-icon">{icon}</span><strong>{title}</strong><p>{text}</p></div>;
}

function useCountdown(competition) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  if (!competition) return 0;
  if (competition.status === "paused") return competition.remainingSeconds || 0;
  if (competition.status !== "running" || !competition.spinEndsAt) return 0;
  return Math.max(0, Math.ceil((new Date(competition.spinEndsAt).getTime() - now) / 1000));
}

function usePolling(callback, intervalMs) {
  const inFlight = useRef(false);
  useEffect(() => {
    let active = true;
    let timeout;
    const poll = async () => {
      if (inFlight.current) {
        if (active) timeout = window.setTimeout(poll, intervalMs);
        return;
      }
      inFlight.current = true;
      try {
        await callback();
      } finally {
        inFlight.current = false;
        if (active) timeout = window.setTimeout(poll, intervalMs);
      }
    };
    poll();
    return () => {
      active = false;
      window.clearTimeout(timeout);
    };
  }, [callback, intervalMs]);
}

function formatTime(totalSeconds) {
  const safe = Math.max(0, Number(totalSeconds) || 0);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;
  return hours > 0
    ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export default App;
