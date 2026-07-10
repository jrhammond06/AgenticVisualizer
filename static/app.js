const state = {
  session: null,
  ws: null,
  thinking: new Set(),
  generating: new Set(), // agent_ids with an active LLM call in step mode
  speaking: null, // agent_id currently speaking
  lastSpeaker: null,
  transcripts: {}, // agent_id -> list of messages
  refereeEvaluations: [], // list of structured evaluations
  lastStatus: "idle",
  stepMode: false,
  circleReady: false,
  activeBubbles: new Map(), // agentId -> bubble element
  speechQueue: [], // realtime speech events waiting to be displayed
  currentSpeech: null, // currently displayed speech event in realtime
  speechTimer: null, // timer enforcing minimum display time
  pendingOutcome: null, // round_over message held until speech queue empties
  pendingRefereePopup: false, // referee_popup flag held until speech queue empties
};

const avatarPool = ["🤖", "🐶", "🐱", "🦊", "🐼", "🐨", "🦁", "🐯", "🐷", "🐸", "🐙", "🦄"];

// DOM refs
const els = {
  topicDisplay: document.getElementById("topic-display"),
  turnOrder: document.getElementById("turn-order"),
  maxTurns: document.getElementById("max-turns"),
  minTurns: document.getElementById("min-turns"),
  modeSelect: document.getElementById("mode-select"),
  agentsList: document.getElementById("agents-list"),
  avatarsContainer: document.getElementById("avatars-container"),
  startBtn: document.getElementById("start-round"),
  nextBtn: document.getElementById("next-step"),
  stopBtn: document.getElementById("stop-round"),
  resetBtn: document.getElementById("reset-round"),
  status: document.getElementById("status-indicator"),
  togglePanel: document.getElementById("toggle-panel"),
  teacherPanel: document.getElementById("teacher-panel"),
  addAgent: document.getElementById("add-agent"),
  outcomeCard: document.getElementById("outcome-card"),
  outcomeTitle: document.getElementById("outcome-title"),
  outcomeBadge: document.getElementById("outcome-badge"),
  outcomeProposal: document.getElementById("outcome-proposal"),
  outcomeDetails: document.getElementById("outcome-details"),
  outcomeSummary: document.getElementById("outcome-summary"),
  closeOutcome: document.getElementById("close-outcome"),
  liveLog: document.getElementById("live-log"),
  transcriptModal: document.getElementById("transcript-modal"),
  transcriptTitle: document.getElementById("transcript-title"),
  transcriptBody: document.getElementById("transcript-body"),
  closeTranscript: document.getElementById("close-transcript"),
};

// WebSocket
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;
  state.ws = new WebSocket(wsUrl);

  state.ws.onopen = () => {
    console.log("WebSocket connected");
  };

  state.ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    handleMessage(msg);
  };

  state.ws.onclose = () => {
    console.log("WebSocket closed, reconnecting in 2s...");
    setTimeout(connectWebSocket, 2000);
  };

  state.ws.onerror = (err) => {
    console.error("WebSocket error", err);
  };
}

function sendWs(type, data = {}) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ type, ...data }));
  }
}

function handleMessage(msg) {
  switch (msg.type) {
    case "session":
      loadSession(msg.data);
      break;
    case "status":
      if (msg.state === "idle" || msg.state === "paused") {
        state.circleReady = false;
        clearGenerating();
      }
      setStatus(msg.state);
      break;
    case "round_started":
      clearBubbles();
      hideOutcome();
      clearTranscripts();
      state.circleReady = false;
      log("🎬 Round started");
      break;
    case "round_resumed":
      clearBubbles();
      hideOutcome();
      log("▶ Round resumed");
      break;
    case "circle_ready":
      state.circleReady = true;
      setStatus("running");
      log(`📦 Circle ready (${msg.steps} steps). Press Next to reveal.`);
      break;
    case "clear_bubbles":
      clearBubbles();
      state.circleReady = false;
      setStatus("running");
      break;
    case "referee_evaluation_bubble":
      if (state.stepMode) {
        showRefereeMessage(msg.content, msg.evaluation);
      } else {
        enqueueSpeech("referee", msg.content, { evaluation: msg.evaluation });
      }
      pushRefereeEvaluation(msg.evaluation);
      log(`🧐 Referee: ${msg.content}`);
      break;
    case "phase":
      log(`📢 ${msg.message}`);
      break;
    case "agent_thinking":
      setThinking(msg.agent_id, true);
      break;
    case "agent_generating":
      setGenerating(msg.agent_id, !msg.done);
      break;
    case "referee_generating":
      setGenerating("referee", !msg.done);
      break;
    case "agent_speak":
      setThinking(msg.agent_id, false);
      // A new agent taking focus should clear any lingering referee warning toast.
      document.querySelectorAll(".referee-warning").forEach((w) => w.remove());
      if (state.stepMode) {
        showSpeech(msg.agent_id, msg.content, { persistent: true });
      } else {
        enqueueSpeech(msg.agent_id, msg.content);
      }
      addTranscript(msg.agent_id, msg.content);
      log(`💬 ${getAgentName(msg.agent_id)}: ${msg.content}`);
      break;
    case "referee_thinking":
      log("🧐 Referee is evaluating...");
      break;
    case "referee_warning":
      showRefereeWarning(msg.content);
      log(`⚠️ Referee: ${msg.content}`);
      break;
    case "referee_evaluation":
      pushRefereeEvaluation(msg.evaluation);
      break;
    case "round_over":
      pushRefereeEvaluation(msg.evaluation);
      state.pendingOutcome = msg;
      tryShowDeferred();
      log(msg.consensus_reached ? `✅ Outcome: ${msg.outcome}` : `⏸ No consensus: ${msg.outcome}`);
      break;
    case "error":
      log(`⚠️ ${msg.message}`);
      alert(msg.message);
      break;
  }
}

// Session loading
function loadSession(data) {
  state.session = data;
  state.thinking.clear();
  state.speaking = null;

  if (document.activeElement !== els.turnOrder) els.turnOrder.value = data.rules.turn_order;
  if (document.activeElement !== els.maxTurns) els.maxTurns.value = data.rules.max_turns;
  if (document.activeElement !== els.minTurns) els.minTurns.value = data.rules.min_turns;
  if (document.activeElement !== els.modeSelect) els.modeSelect.value = data.rules.mode || "realtime";

  state.stepMode = (data.rules.mode || "realtime") === "step_by_step";
  updateButtonVisibility();

  els.topicDisplay.textContent = data.topic;

  // Show loaded package banner if a package is loaded.
  const pkgSection = document.getElementById("package-section");
  const pkgBanner = document.getElementById("package-banner");
  if (data.loaded_package_name) {
    pkgBanner.innerHTML = `<strong>${escapeHtml(data.loaded_package_name)}</strong><br>
      <span style="font-size:0.85rem;color:var(--text-muted)">${escapeHtml(data.topic)}</span>`;
    pkgSection.style.display = "";
  } else {
    pkgSection.style.display = "none";
  }

  // Rebuild per-agent transcripts from session history.
  state.transcripts = {};
  (data.history || []).forEach((msg) => {
    if (msg.agent_id && msg.agent_id !== "referee") addTranscript(msg.agent_id, msg.content);
  });

  state.refereeEvaluations = [];
  if (data.last_evaluation) state.refereeEvaluations.push(data.last_evaluation);

  renderAgentList();
  renderAvatars();
  setStatus(data.status);
}

// Status
function setStatus(status) {
  const wasRunning = state.lastStatus === "running";
  state.lastStatus = status;

  const displayStatus = state.circleReady ? "waiting" : status;
  els.status.textContent = state.circleReady ? "waiting for next" : status;
  els.status.className = `status ${displayStatus}`;

  const active = status === "running" || state.circleReady;
  els.startBtn.disabled = active;
  els.startBtn.textContent = status === "paused" ? "▶ Resume Round" : "▶ Start Round";
  els.stopBtn.disabled = !active;
  els.nextBtn.disabled = !state.circleReady;

  // Open the referee modal when the simulation just paused after a running cycle,
  // but wait until any queued speech bubbles have finished.
  if (status === "paused" && wasRunning) {
    state.pendingRefereePopup = true;
    tryShowDeferred();
  }
}

function updateButtonVisibility() {
  els.nextBtn.style.display = state.stepMode ? "" : "none";
}

// Agent helpers
function getAgent(id) {
  return state.session?.agents.find((a) => a.id === id);
}

function getAgentName(id) {
  if (id === "referee") return "Referee";
  return getAgent(id)?.name || "Agent";
}


// Rendering avatars in a circle
function renderAvatars() {
  if (!state.session) return;
  const container = els.avatarsContainer;
  container.innerHTML = "";

  const agents = state.session.agents;
  if (agents.length === 0) {
    container.innerHTML = '<div class="empty-room">Add agents to start</div>';
    return;
  }

  const radius = 28; // percent of container
  const center = 50;

  agents.forEach((agent, i) => {
    const angle = (2 * Math.PI * i) / agents.length - Math.PI / 2;
    const left = center + radius * Math.cos(angle);
    const top = center + radius * Math.sin(angle);

    const el = document.createElement("div");
    el.className = "avatar";
    el.id = `avatar-${agent.id}`;
    el.style.left = `${left}%`;
    el.style.top = `${top}%`;

    const face = document.createElement("div");
    face.className = "avatar-face";
    face.textContent = agent.avatar;

    const name = document.createElement("div");
    name.className = "avatar-name";
    name.textContent = agent.name;

    el.appendChild(face);
    el.appendChild(name);
    el.addEventListener("click", () => showTranscript(agent.id));
    container.appendChild(el);
  });

  // Add a clickable referee avatar in the center.
  const referee = document.createElement("div");
  referee.className = "avatar referee-avatar";
  referee.id = "avatar-referee";
  referee.style.left = "50%";
  referee.style.top = "50%";
  referee.title = "Click to see referee assessments";
  const refereeFace = document.createElement("div");
  refereeFace.className = "avatar-face";
  refereeFace.textContent = "🧐";
  const refereeName = document.createElement("div");
  refereeName.className = "avatar-name";
  refereeName.textContent = "Referee";
  referee.appendChild(refereeFace);
  referee.appendChild(refereeName);
  referee.addEventListener("click", () => showRefereeEvaluations());
  container.appendChild(referee);
}

// Agent list — compact read-only rows with an expand toggle for full editing.
function renderAgentList() {
  if (!state.session) return;
  const focused = els.agentsList.querySelector("input:focus, textarea:focus, select:focus");
  if (focused) return;

  els.agentsList.innerHTML = "";

  state.session.agents.forEach((agent) => {
    const card = document.createElement("div");
    card.className = "agent-card";
    card.dataset.id = agent.id;

    card.innerHTML = `
      <div class="agent-header">
        <span style="font-size:1.4rem">${escapeHtml(agent.avatar)}</span>
        <span class="agent-name-input" style="flex:1;font-weight:700">${escapeHtml(agent.name)}</span>
        <button class="small-btn" style="font-size:0.75rem;padding:4px 8px"
                onclick="toggleAgentEdit('${agent.id}')">Edit</button>
        <button class="delete-agent" title="Remove" onclick="deleteAgent('${agent.id}')">✕</button>
      </div>
      <div id="agent-edit-${agent.id}" style="display:none;margin-top:8px">
        <div style="display:flex;gap:6px;margin-bottom:6px;align-items:center">
          <select class="agent-avatar-picker" data-field="avatar">${avatarPool
            .map((a) => `<option value="${a}" ${a === agent.avatar ? "selected" : ""}>${a}</option>`)
            .join("")}</select>
          <input type="text" data-field="name" value="${escapeHtml(agent.name)}"
                 placeholder="Name" style="flex:1">
        </div>
        <input type="text" data-field="goal" value="${escapeHtml(agent.goal)}"
               placeholder="Visible goal" style="margin-bottom:6px">
        <textarea data-field="system_prompt" placeholder="System prompt"
                  style="min-height:80px">${escapeHtml(agent.system_prompt)}</textarea>
        <button class="small-btn" style="margin-top:6px"
                onclick="saveAgentEdit('${agent.id}')">Save</button>
      </div>
    `;

    els.agentsList.appendChild(card);
  });
}

function toggleAgentEdit(id) {
  const el = document.getElementById(`agent-edit-${id}`);
  el.style.display = el.style.display === "none" ? "" : "none";
}

function saveAgentEdit(id) {
  const card = els.agentsList.querySelector(`[data-id="${id}"]`);
  if (!card) return;
  const update = {};
  card.querySelectorAll("[data-field]").forEach((el) => {
    update[el.dataset.field] = el.value;
  });
  updateAgent(id, update);
  toggleAgentEdit(id);
}

// Visual effects
function setThinking(agentId, thinking) {
  const el = document.getElementById(`avatar-${agentId}`);
  if (!el) return;

  if (thinking) {
    state.thinking.add(agentId);
    el.classList.add("thinking");
    if (!el.querySelector(".thinking-bubble")) {
      const bubble = document.createElement("div");
      bubble.className = "thinking-bubble";
      bubble.textContent = "Thinking…";
      el.appendChild(bubble);
    }
  } else {
    state.thinking.delete(agentId);
    el.classList.remove("thinking");
    const bubble = el.querySelector(".thinking-bubble");
    if (bubble) bubble.remove();
  }
}

function showSpeech(agentId, content, options = {}) {
  const { persistent = false } = options;
  const el = document.getElementById(`avatar-${agentId}`);
  if (!el) return;

  if (state.stepMode) {
    // Step mode: keep earlier bubbles visible; just remove this agent's old bubble.
    const existing = state.activeBubbles.get(agentId);
    if (existing) {
      existing.remove();
      state.activeBubbles.delete(agentId);
    }
  } else {
    // Realtime: only one speech bubble at a time.
    clearAllSpeechBubbles();
  }

  document.querySelectorAll(".avatar.speaking").forEach((a) => a.classList.remove("speaking"));

  state.speaking = agentId;
  state.lastSpeaker = agentId;
  el.classList.add("speaking");

  const bubble = document.createElement("div");
  bubble.className = "speech-bubble";
  bubble.textContent = content;
  bubble.dataset.agentId = agentId;
  els.avatarsContainer.appendChild(bubble);

  state.activeBubbles.set(agentId, bubble);

  // Position after the browser has measured the bubble.
  requestAnimationFrame(() => {
    positionBubbles();
  });

  // Auto-remove after 5 seconds unless a newer bubble for this agent exists.
  if (!persistent) {
    setTimeout(() => {
      if (state.activeBubbles.get(agentId) === bubble) {
        bubble.remove();
        state.activeBubbles.delete(agentId);
        if (state.speaking === agentId) {
          el.classList.remove("speaking");
          state.speaking = null;
        }
      }
    }, 5000);
  }
}

function pushRefereeEvaluation(evaluation) {
  if (!evaluation) return;
  const last = state.refereeEvaluations[state.refereeEvaluations.length - 1];
  if (last && JSON.stringify(last) === JSON.stringify(evaluation)) return;
  state.refereeEvaluations.push(evaluation);
}

function showRefereeMessage(content, evaluation) {
  const warnings = evaluation?.warnings || [];
  if (warnings.length > 0) {
    // Warnings are the single live referee message; the full list is in the modal.
    showRefereeWarning(warnings[0]);
  } else {
    showRefereeSpeech(content);
  }
}

function showRefereeSpeech(content) {
  const el = document.getElementById("avatar-referee");
  if (!el) return;

  // A speech bubble replaces any transient referee warning.
  document.querySelectorAll(".referee-warning").forEach((w) => w.remove());

  if (state.stepMode) {
    // Remove any existing referee bubble.
    const existing = state.activeBubbles.get("referee");
    if (existing) {
      existing.remove();
      state.activeBubbles.delete("referee");
    }
  } else {
    // Realtime: only one speech bubble at a time.
    clearAllSpeechBubbles();
  }

  document.querySelectorAll(".avatar.speaking").forEach((a) => a.classList.remove("speaking"));

  state.speaking = "referee";
  state.lastSpeaker = "referee";
  el.classList.add("speaking");

  const bubble = document.createElement("div");
  bubble.className = "speech-bubble referee-speech-bubble";
  bubble.textContent = content;
  bubble.dataset.agentId = "referee";
  els.avatarsContainer.appendChild(bubble);

  state.activeBubbles.set("referee", bubble);

  requestAnimationFrame(() => {
    positionBubbles();
  });
}

function clearAllSpeechBubbles() {
  document.querySelectorAll(".speech-bubble").forEach((b) => b.remove());
  document.querySelectorAll(".referee-warning").forEach((w) => w.remove());
  state.activeBubbles.clear();
}

function positionBubbles() {
  const container = els.avatarsContainer;
  const containerRect = container.getBoundingClientRect();
  const referee = document.getElementById("avatar-referee");

  // Referee bounding box with a small safety margin.
  let refereeRect = null;
  if (referee) {
    const r = referee.getBoundingClientRect();
    const margin = 12;
    refereeRect = {
      left: r.left - containerRect.left - margin,
      top: r.top - containerRect.top - margin,
      right: r.right - containerRect.left + margin,
      bottom: r.bottom - containerRect.top + margin,
    };
  }

  // Build avatar rects (excluding the speaker being placed) for overlap avoidance.
  const avatarRects = [];
  document.querySelectorAll(".avatar").forEach((av) => {
    const r = av.getBoundingClientRect();
    avatarRects.push({
      left: r.left - containerRect.left,
      top: r.top - containerRect.top,
      right: r.right - containerRect.left,
      bottom: r.bottom - containerRect.top,
    });
  });

  const placedRects = [];

  state.activeBubbles.forEach((bubble, agentId) => {
    const avatar = document.getElementById(`avatar-${agentId}`);
    if (!avatar) return;

    const avatarRect = avatar.getBoundingClientRect();
    const avatarCx = avatarRect.left + avatarRect.width / 2 - containerRect.left;
    const avatarCy = avatarRect.top + avatarRect.height / 2 - containerRect.top;

    // Measure the bubble at a temporary origin.
    bubble.style.visibility = "hidden";
    bubble.style.left = "0px";
    bubble.style.top = "0px";
    const bubbleRect = bubble.getBoundingClientRect();
    const bw = bubbleRect.width;
    const bh = bubbleRect.height;

    // Unit vector pointing from container center through the avatar (radially outward).
    const dx = avatarCx - containerRect.width / 2;
    const dy = avatarCy - containerRect.height / 2;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const ux = dx / dist;
    const uy = dy / dist;

    // Generate candidates: radial distances plus angular deviations.
    const candidates = [];
    const distances = [70, 95, 125, 165, 210, 260];
    const angles = [0, -0.3, 0.3, -0.6, 0.6, -0.9, 0.9]; // radians

    angles.forEach((angle) => {
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      // Rotate the outward unit vector by this angle.
      const rx = ux * cos - uy * sin;
      const ry = ux * sin + uy * cos;

      distances.forEach((d) => {
        const cx = avatarCx + rx * d;
        const cy = avatarCy + ry * d;
        candidates.push({
          cx,
          cy,
          dir: { x: rx, y: ry },
          distance: d,
          rect: {
            left: cx - bw / 2,
            top: cy - bh / 2,
            right: cx + bw / 2,
            bottom: cy + bh / 2,
            width: bw,
            height: bh,
          },
        });
      });
    });

    let best = null;
    let bestScore = Infinity;

    candidates.forEach((cand) => {
      let score = 0;

      // 1. Penalize going outside the avatar container (heavy).
      if (cand.rect.left < 0) score += 2000 + Math.abs(cand.rect.left) * 5;
      if (cand.rect.top < 0) score += 2000 + Math.abs(cand.rect.top) * 5;
      if (cand.rect.right > containerRect.width) {
        score += 2000 + (cand.rect.right - containerRect.width) * 5;
      }
      if (cand.rect.bottom > containerRect.height) {
        score += 2000 + (cand.rect.bottom - containerRect.height) * 5;
      }

      // 2. Heavily penalize overlapping the referee.
      if (refereeRect && rectsOverlap(cand.rect, refereeRect)) {
        score += 10000;
      }

      // 3. Penalize overlapping other agent avatars.
      avatarRects.forEach((ar) => {
        if (rectsOverlap(cand.rect, ar)) {
          score += 8000;
        }
      });

      // 4. Penalize overlapping already-placed bubbles.
      placedRects.forEach((pr) => {
        if (rectsOverlap(cand.rect, pr)) {
          score += 5000;
        }
      });

      // 5. Prefer directions close to radially outward.
      const alignment = ux * cand.dir.x + uy * cand.dir.y;
      score -= alignment * 100;

      // 6. Prefer candidates closer to the avatar (keeps bubble near speaker).
      score += cand.distance * 3;

      if (score < bestScore) {
        bestScore = score;
        best = cand;
      }
    });

    if (best) {
      bubble.style.left = `${best.rect.left}px`;
      bubble.style.top = `${best.rect.top}px`;
      bubble.style.visibility = "visible";

      // Apply an arrow class pointing back toward the avatar.
      bubble.classList.remove("arrow-top", "arrow-bottom", "arrow-left", "arrow-right");
      const toAvatarX = avatarCx - best.cx;
      const toAvatarY = avatarCy - best.cy;
      if (Math.abs(toAvatarX) > Math.abs(toAvatarY)) {
        bubble.classList.add(toAvatarX > 0 ? "arrow-right" : "arrow-left");
      } else {
        bubble.classList.add(toAvatarY > 0 ? "arrow-bottom" : "arrow-top");
      }

      placedRects.push(best.rect);
    }
  });
}

function rectsOverlap(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

function clearBubbles() {
  document.querySelectorAll(".speech-bubble").forEach((b) => b.remove());
  document.querySelectorAll(".referee-warning").forEach((w) => w.remove());
  document.querySelectorAll(".avatar.speaking").forEach((a) => a.classList.remove("speaking"));
  document.querySelectorAll(".thinking-bubble").forEach((b) => b.remove());
  document.querySelectorAll(".avatar.thinking").forEach((a) => a.classList.remove("thinking"));
  clearGenerating();
  state.thinking.clear();
  state.speaking = null;
  state.activeBubbles.clear();
  state.speechQueue = [];
  state.currentSpeech = null;
  state.pendingOutcome = null;
  state.pendingRefereePopup = false;
  if (state.speechTimer) {
    clearTimeout(state.speechTimer);
    state.speechTimer = null;
  }
}

function enqueueSpeech(agentId, content, options = {}) {
  state.speechQueue.push({ agentId, content, options });
  processSpeechQueue();
}

function processSpeechQueue() {
  if (state.currentSpeech) {
    const elapsed = Date.now() - state.currentSpeech.shownAt;
    const duration = state.currentSpeech.duration || 5000;
    if (elapsed >= duration && state.speechQueue.length > 0) {
      advanceSpeech();
    }
    tryShowDeferred();
    return;
  }

  if (state.speechQueue.length === 0) {
    tryShowDeferred();
    return;
  }

  const next = state.speechQueue.shift();
  displaySpeech(next.agentId, next.content, next.options);
}

function displaySpeech(agentId, content, options = {}) {
  if (agentId === "referee") {
    showRefereeMessage(content, options.evaluation);
  } else {
    showSpeech(agentId, content, { persistent: true });
  }
  // When the referee shows a warning banner, hold the slot as long as the banner
  // lives (8s) so the queue doesn't advance while the warning is still on screen.
  // For a plain status summary (no warnings), 4s is enough to read.
  let duration = 5000;
  if (agentId === "referee") {
    const hasWarnings = (options.evaluation?.warnings?.length ?? 0) > 0;
    duration = hasWarnings ? 8000 : 4000;
  }
  state.currentSpeech = { agentId, content, shownAt: Date.now(), duration };
  if (state.speechTimer) {
    clearTimeout(state.speechTimer);
  }
  state.speechTimer = setTimeout(() => {
    state.speechTimer = null;
    onMinDisplayTimeElapsed();
  }, duration);
}

function onMinDisplayTimeElapsed() {
  if (state.speechQueue.length > 0) {
    advanceSpeech();
  }
  // If the queue is empty, keep the current bubble until the next response arrives.
  tryShowDeferred();
}

function advanceSpeech() {
  if (!state.currentSpeech) return;
  removeCurrentSpeech();
  processSpeechQueue();
}

function removeCurrentSpeech() {
  if (!state.currentSpeech) return;
  const { agentId } = state.currentSpeech;
  // Do NOT remove .referee-warning here — the banner has its own 8s timer set in
  // showRefereeWarning and should outlive the speech queue slot. Removing it here
  // caused warnings to disappear after only 3s regardless of the banner's timeout.
  const bubble = state.activeBubbles.get(agentId);
  if (bubble) {
    bubble.remove();
    state.activeBubbles.delete(agentId);
  }
  const el = document.getElementById(`avatar-${agentId}`);
  if (el && state.speaking === agentId) {
    el.classList.remove("speaking");
    state.speaking = null;
  }
  state.currentSpeech = null;
  if (state.speechTimer) {
    clearTimeout(state.speechTimer);
    state.speechTimer = null;
  }
  tryShowDeferred();
}

function tryShowDeferred() {
  if (state.speechQueue.length > 0) return;

  const hasDeferred = state.pendingOutcome || state.pendingRefereePopup;

  // If a speech bubble is still on screen but has met its minimum display time,
  // clear it so round-end or popup UI can take focus.
  if (state.currentSpeech) {
    const elapsed = Date.now() - state.currentSpeech.shownAt;
    const duration = state.currentSpeech.duration || 5000;
    if (hasDeferred && elapsed >= duration) {
      removeCurrentSpeech();
    } else {
      return;
    }
  }

  if (state.pendingOutcome) {
    state.pendingOutcome = null;
    hideOutcome();
    if (els.transcriptModal.classList.contains("hidden")) {
      showRefereeEvaluations(true);
    }
  }

  if (state.pendingRefereePopup) {
    state.pendingRefereePopup = false;
    if (els.transcriptModal.classList.contains("hidden") && state.refereeEvaluations.length > 0) {
      showRefereeEvaluations(false);
    }
  }
}

function setGenerating(agentId, generating) {
  const el = document.getElementById(`avatar-${agentId}`);
  if (!el) return;

  if (generating) {
    state.generating.add(agentId);
    el.classList.add("generating");
    if (!el.querySelector(".generating-bubble")) {
      const bubble = document.createElement("div");
      bubble.className = "generating-bubble";
      bubble.textContent = "⚙️";
      el.appendChild(bubble);
    }
  } else {
    state.generating.delete(agentId);
    el.classList.remove("generating");
    const bubble = el.querySelector(".generating-bubble");
    if (bubble) bubble.remove();
  }
}

function clearGenerating() {
  state.generating.forEach((agentId) => setGenerating(agentId, false));
  setGenerating("referee", false);
  state.generating.clear();
}

function clearTranscripts() {
  state.transcripts = {};
  state.refereeEvaluations = [];
}

function addTranscript(agentId, content) {
  if (!state.transcripts[agentId]) {
    state.transcripts[agentId] = [];
  }
  state.transcripts[agentId].push(content);
}

function showTranscript(agentId) {
  const agent = getAgent(agentId);
  const name = agent ? agent.name : "Agent";
  els.transcriptTitle.textContent = `${agent ? agent.avatar : "🤖"} ${name}`;
  const messages = state.transcripts[agentId] || [];
  if (messages.length === 0) {
    els.transcriptBody.innerHTML = `<p class="empty-transcript">${name} hasn't spoken yet this round.</p>`;
  } else {
    els.transcriptBody.innerHTML = messages
      .map((m) => `<div class="transcript-entry">${escapeHtml(m)}</div>`)
      .join("");
  }
  els.transcriptModal.classList.remove("hidden");
}

function showRefereeEvaluations(isFinal = false) {
  // A focused assessment replaces any transient referee message.
  document.querySelectorAll(".referee-warning").forEach((w) => w.remove());
  const refereeBubble = state.activeBubbles.get("referee");
  if (refereeBubble) {
    refereeBubble.remove();
    state.activeBubbles.delete("referee");
  }
  const refereeAvatar = document.getElementById("avatar-referee");
  if (refereeAvatar && state.speaking === "referee") {
    refereeAvatar.classList.remove("speaking");
    state.speaking = null;
  }

  els.transcriptTitle.textContent = isFinal ? "🧐 Where Things Stand" : "🧐 Referee Assessments";
  // End-of-run report should only show the final evaluation, not the history of
  // interim assessments from each cycle.
  const evaluationsToRender = isFinal
    ? state.refereeEvaluations.slice(-1)
    : state.refereeEvaluations;
  if (evaluationsToRender.length === 0) {
    els.transcriptBody.innerHTML = `<p class="empty-transcript">The referee hasn't evaluated the round yet.</p>`;
  } else {
    els.transcriptBody.innerHTML = evaluationsToRender
      .map((evaluation, i) => {
        const checklist = evaluation.checklist || {};
        const checklistHtml = Object.entries(checklist)
          .map(([key, item]) => {
            const status = (item.status || "unknown").toLowerCase();
            const note = item.note || "";
            return `<div class="checklist-item ${status}"><strong>${escapeHtml(key)}:</strong> <span class="status">${escapeHtml(status)}</span>${note ? ` — ${escapeHtml(note)}` : ""}</div>`;
          })
          .join("");
        const proposalHtml = evaluation.consensus_reached && evaluation.consensus_proposal
          ? `<div class="eval-proposal"><strong>Consensus proposal:</strong> ${escapeHtml(evaluation.consensus_proposal)}</div>`
          : "";
        const detailsHtml = evaluation.consensus_reached && evaluation.proposal_details && Object.keys(evaluation.proposal_details).length
          ? `<div class="eval-details">
              <button class="collapse-toggle" data-target="referee-details-${i}" data-label="details">Show details ▶</button>
              <div id="referee-details-${i}" class="collapse-content hidden">
                <pre>${escapeHtml(JSON.stringify(evaluation.proposal_details, null, 2))}</pre>
              </div>
            </div>`
          : "";
        const headerText = isFinal ? "Final Assessment" : `Assessment #${i + 1}`;
        return `
          <div class="evaluation-entry">
            <div class="eval-header">${headerText}${evaluation.consensus_reached ? " ✅ Consensus" : ""}</div>
            <div class="eval-summary">${escapeHtml(evaluation.status_summary || "")}</div>
            <div class="checklist">${checklistHtml}</div>
            ${proposalHtml}
            ${detailsHtml}
          </div>
        `;
      })
      .join("");

    els.transcriptBody.querySelectorAll(".collapse-toggle").forEach((button) => {
      button.addEventListener("click", () => toggleCollapse(button));
    });
  }
  els.transcriptModal.classList.remove("hidden");
}

function hideTranscriptModal() {
  els.transcriptModal.classList.add("hidden");
}

function showOutcome(outcome, summary, consensusProposal, proposalDetails, consensusReached) {
  els.outcomeTitle.textContent = outcome || (consensusReached ? "Consensus Reached" : "No Consensus");

  if (consensusReached) {
    els.outcomeBadge.textContent = "🎉 Consensus Reached";
    els.outcomeBadge.className = "outcome-badge";
  } else {
    els.outcomeBadge.textContent = "⏸ Where Things Stand";
    els.outcomeBadge.className = "outcome-badge no-consensus";
  }

  if (consensusProposal) {
    els.outcomeProposal.innerHTML = `<strong>Proposal:</strong> ${escapeHtml(consensusProposal)}`;
    els.outcomeProposal.classList.remove("hidden");
  } else {
    els.outcomeProposal.innerHTML = "No proposal decided.";
    els.outcomeProposal.classList.remove("hidden");
  }

  if (proposalDetails && Object.keys(proposalDetails).length > 0) {
    els.outcomeDetails.innerHTML = `<strong>Details:</strong>
      <button class="collapse-toggle" data-target="outcome-details-content" data-label="details">Show details ▶</button>
      <div id="outcome-details-content" class="collapse-content hidden">
        <pre>${escapeHtml(JSON.stringify(proposalDetails, null, 2))}</pre>
      </div>`;
    els.outcomeDetails.classList.remove("hidden");
    const toggle = els.outcomeDetails.querySelector(".collapse-toggle");
    if (toggle) toggle.addEventListener("click", () => toggleCollapse(toggle));
  } else {
    els.outcomeDetails.innerHTML = "";
    els.outcomeDetails.classList.add("hidden");
  }

  els.outcomeSummary.textContent = summary || "";
  els.outcomeCard.classList.remove("hidden");
}

function hideOutcome() {
  els.outcomeCard.classList.add("hidden");
}

function showRefereeWarning(content) {
  // Remove any existing warning and the current referee speech bubble so only
  // one live referee message is visible at a time.
  document.querySelectorAll(".referee-warning").forEach((el) => el.remove());
  const refereeBubble = state.activeBubbles.get("referee");
  if (refereeBubble) {
    refereeBubble.remove();
    state.activeBubbles.delete("referee");
  }
  const refereeAvatar = document.getElementById("avatar-referee");
  if (refereeAvatar && state.speaking === "referee") {
    refereeAvatar.classList.remove("speaking");
    state.speaking = null;
  }

  const warning = document.createElement("div");
  warning.className = "referee-warning";
  warning.innerHTML = `<strong>Referee:</strong> ${escapeHtml(content)}`;
  document.getElementById("room").appendChild(warning);

  setTimeout(() => {
    warning.remove();
  }, 8000);
}

// Logging
function log(text) {
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.textContent = text;
  els.liveLog.appendChild(entry);
  els.liveLog.scrollTop = els.liveLog.scrollHeight;
}

// API / WS actions
function updateRules() {
  sendWs("update_session", {
    data: {
      rules: {
        turn_order: els.turnOrder.value,
        max_turns: parseInt(els.maxTurns.value, 10),
        min_turns: parseInt(els.minTurns.value, 10),
        mode: els.modeSelect.value,
      },
    },
  });
}

function updateAgent(id, update) {
  const agent = getAgent(id);
  if (!agent) return;
  const updated = { ...agent, ...update };
  const agents = state.session.agents.map((a) => (a.id === id ? updated : a));
  sendWs("update_session", { data: { agents } });
}

function addAgent() {
  const idx = state.session.agents.length % avatarPool.length;
  const newAgent = {
    name: `Agent ${state.session.agents.length + 1}`,
    avatar: avatarPool[idx],
    goal: "Help the group reach a good decision.",
    system_prompt: "You are a thoughtful participant. Keep replies short and constructive.",
  };
  sendWs("update_session", { data: { agents: [...state.session.agents, newAgent] } });
}

function deleteAgent(id) {
  sendWs("update_session", {
    data: { agents: state.session.agents.filter((a) => a.id !== id) },
  });
}

function startRound() {
  sendWs("start_round");
}

function stopRound() {
  sendWs("stop_round");
}

async function resetRound() {
  try {
    const res = await fetch("/api/session/reset", { method: "POST" });
    if (!res.ok) {
      const err = await res.json();
      alert(err.detail || "Reset failed");
    }
  } catch (e) {
    alert("Reset failed: " + e.message);
  }
}

// Utility
function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function toggleCollapse(button) {
  const target = document.getElementById(button.dataset.target);
  if (!target) return;
  target.classList.toggle("hidden");
  const label = button.dataset.label || "details";
  button.textContent = target.classList.contains("hidden")
    ? `Show ${label} ▶`
    : `Hide ${label} ▼`;
}

// Event listeners
els.togglePanel.addEventListener("click", () => {
  els.teacherPanel.classList.toggle("open");
  els.teacherPanel.classList.toggle("closed");
  setTimeout(positionBubbles, 300);
});

els.turnOrder.addEventListener("change", updateRules);
els.maxTurns.addEventListener("change", updateRules);
els.minTurns.addEventListener("change", updateRules);
els.modeSelect.addEventListener("change", updateRules);

els.startBtn.addEventListener("click", startRound);
els.nextBtn.addEventListener("click", () => sendWs("next_step"));
els.stopBtn.addEventListener("click", stopRound);
els.resetBtn.addEventListener("click", resetRound);
els.addAgent.addEventListener("click", addAgent);
els.closeOutcome.addEventListener("click", hideOutcome);
els.closeTranscript.addEventListener("click", hideTranscriptModal);
els.transcriptModal.addEventListener("click", (e) => {
  if (e.target === els.transcriptModal) hideTranscriptModal();
});

window.addEventListener("resize", () => {
  positionBubbles();
});

// Initial connect
connectWebSocket();
