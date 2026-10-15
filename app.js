"use strict";

const elements = {
  count: document.querySelector("#participant-count"),
  rounds: document.querySelector("#round-count"),
  status: document.querySelector("#round-status"),
  statusNote: document.querySelector("#status-note"),
  nodes: document.querySelector("#participant-nodes"),
  stage: document.querySelector("#circle-stage"),
  centerpiece: document.querySelector("#centerpiece"),
  centerLabel: document.querySelector("#center-label"),
  centerSubtitle: document.querySelector("#center-subtitle"),
  resultLabel: document.querySelector("#result-label"),
  resultText: document.querySelector("#result-text"),
  resultDetail: document.querySelector("#result-detail"),
  guestList: document.querySelector("#guest-list"),
  guestLimit: document.querySelector("#guest-limit"),
  history: document.querySelector("#history-list"),
  historyCount: document.querySelector("#history-count"),
  checkpoints: document.querySelector("#sidebar-checkpoints"),
  spin: document.querySelector("#spin-button"),
  spinLabel: document.querySelector("#spin-label"),
  spinHint: document.querySelector("#spin-hint"),
  addForm: document.querySelector("#add-form"),
  input: document.querySelector("#participant-input"),
  direction: document.querySelector("#direction-select"),
  toast: document.querySelector("#toast-region"),
  checkpointModal: document.querySelector("#checkpoint-modal"),
  checkpointForm: document.querySelector("#checkpoint-form"),
  checkpointName: document.querySelector("#checkpoint-name"),
  confirmModal: document.querySelector("#confirm-modal"),
};

let state = null;
let mode = "winner";
let busy = false;
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

async function request(path, payload) {
  const response = await fetch(path, {
    method: payload === undefined ? "GET" : "POST",
    headers: payload === undefined ? {} : { "Content-Type": "application/json" },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status}).`);
  return body;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function notify(message, isError = false) {
  const toast = document.createElement("div");
  toast.className = `toast${isError ? " error" : ""}`;
  toast.textContent = message;
  elements.toast.append(toast);
  window.setTimeout(() => toast.remove(), 3600);
}

function setBusy(value) {
  busy = value;
  const finished = state?.status === "finished";
  const participantCount = state?.participants.length ?? 0;
  elements.spin.disabled = value || finished || participantCount < 2;
  elements.spinLabel.textContent = value ? "The circle is turning..." : "Spin the circle";
  elements.addForm.querySelector("button").disabled = value || finished || participantCount >= 32;
  elements.input.disabled = value || finished || participantCount >= 32;
  document.querySelector("#reset-button").disabled = value;
}

function render() {
  if (!state) return;
  const participants = state.participants;
  const count = participants.length;
  elements.count.textContent = String(count).padStart(2, "0");
  elements.rounds.textContent = String(state.round_count).padStart(2, "0");
  elements.status.textContent = state.status === "finished" ? "Complete" : "Ready";
  elements.statusNote.textContent = state.status === "finished"
    ? (state.last_result?.mode === "winner"
      ? "A winner has been selected"
      : `${participants[0]?.name || "A champion"} is the last one standing`)
    : "Waiting for the next spin";
  elements.centerLabel.textContent = state.status === "finished" ? "DRAW COMPLETE" : "THE CIRCLE";
  elements.centerSubtitle.textContent = state.status === "finished" ? "ROUND FINISHED" : "IS READY";
  elements.spinHint.textContent = state.status === "finished"
    ? "Create a checkpoint or reset to begin another round."
    : count < 2 ? "Add at least two participants to spin." : "Fair, random, and ready to decide.";

  elements.nodes.replaceChildren();
  const radius = 35;
  participants.forEach((participant, index) => {
    const angle = (-90 + (360 * index) / count) * (Math.PI / 180);
    const node = document.createElement("div");
    node.className = `participant-node${participant.is_current ? " current" : ""}`;
    node.dataset.participantId = participant.id;
    node.style.left = `${50 + radius * Math.cos(angle)}%`;
    node.style.top = `${50 + radius * Math.sin(angle)}%`;
    node.innerHTML = `<span class="node-number">${String(index + 1).padStart(2, "0")}</span><span class="node-name" title="${escapeHtml(participant.name)}">${escapeHtml(participant.name)}</span>`;
    elements.nodes.append(node);
  });

  elements.guestList.innerHTML = participants.map((participant) =>
    `<span class="guest-chip${participant.is_current ? " current-chip" : ""}" title="${escapeHtml(participant.name)}">${escapeHtml(participant.name)}</span>`
  ).join("");
  elements.guestLimit.textContent = `${count} / 32`;
  elements.addForm.querySelector("button").disabled = busy || state.status === "finished" || count >= 32;
  elements.input.disabled = busy || state.status === "finished" || count >= 32;
  elements.historyCount.textContent = `${state.history.length} EVENT${state.history.length === 1 ? "" : "S"}`;
  elements.history.innerHTML = state.history.length
    ? state.history.slice(0, 6).map((event) =>
      `<article class="history-item"><strong>${escapeHtml(event.title)}</strong><p>${escapeHtml(event.detail)}</p><time>${formatTime(event.time)}</time></article>`
    ).join("")
    : '<p class="history-empty">Your activity will show up here.</p>';
  elements.checkpoints.innerHTML = state.checkpoints.length
    ? state.checkpoints.map((checkpoint) =>
      `<button class="sidebar-checkpoint" type="button" data-checkpoint-id="${escapeHtml(checkpoint.id)}" title="Restore ${escapeHtml(checkpoint.name)}"><span>◷</span>${escapeHtml(checkpoint.name)}</button>`
    ).join("")
    : '<p class="empty-checkpoints">Your saved moments will appear here.</p>';
  renderResult();
  setBusy(busy);
}

function formatTime(value) {
  const date = new Date(value);
  return new Intl.DateTimeFormat("en", { hour: "numeric", minute: "2-digit" }).format(date);
}

function renderResult() {
  const result = state?.last_result;
  if (!result) {
    elements.resultLabel.textContent = "LAST RESULT";
    elements.resultText.textContent = "Ready when you are.";
    elements.resultDetail.textContent = "—";
    return;
  }
  elements.resultLabel.textContent = result.mode === "winner" ? "THE WINNER" : "LAST ELIMINATED";
  elements.resultText.textContent = result.participant_name;
  elements.resultDetail.textContent = `${result.steps} steps · ${result.direction}`;
}

async function animateDraw(result) {
  const nodes = [...elements.nodes.querySelectorAll(".participant-node")];
  const byId = new Map(nodes.map((node) => [node.dataset.participantId, node]));
  const delay = prefersReducedMotion.matches ? 35 : Math.max(95, 250 - result.steps * 4);
  elements.stage.classList.add("is-spinning");
  elements.centerLabel.textContent = "SPINNING";
  elements.centerSubtitle.textContent = `${result.steps} RANDOM STEPS`;
  for (const participantId of result.path) {
    nodes.forEach((node) => node.classList.remove("current", "visited", "selected-node"));
    const node = byId.get(participantId);
    if (node) node.classList.add("current");
    await new Promise((resolve) => window.setTimeout(resolve, delay));
    if (node) node.classList.replace("current", "visited");
  }
  const selectedNode = byId.get(result.participant_id);
  if (selectedNode) {
    selectedNode.classList.remove("visited", "current");
    selectedNode.classList.add("selected-node");
  }
  elements.stage.classList.remove("is-spinning");
  if (result.mode === "eliminate" && selectedNode) {
    selectedNode.classList.add("eliminating");
    await new Promise((resolve) => window.setTimeout(resolve, prefersReducedMotion.matches ? 35 : 330));
  } else {
    await new Promise((resolve) => window.setTimeout(resolve, prefersReducedMotion.matches ? 25 : 220));
  }
}

async function spin() {
  if (busy || !state || state.status === "finished" || state.participants.length < 2) return;
  setBusy(true);
  try {
    const result = await request("/api/spin", { mode, direction: elements.direction.value });
    await animateDraw(result);
    state = result.state;
    setBusy(false);
    render();
    if (result.mode === "winner") {
      elements.resultLabel.textContent = "THE WINNER";
      notify(`${result.participant_name} won the draw!`);
    } else if (state.status === "finished") {
      notify(`${state.participants[0].name} is the last one standing!`);
    } else {
      elements.resultLabel.textContent = "LAST ELIMINATED";
      notify(`${result.participant_name} is out. ${state.participants.length} remain.`);
    }
  } catch (error) {
    elements.stage.classList.remove("is-spinning");
    notify(error.message, true);
    setBusy(false);
  }
}

async function addParticipant(event) {
  event.preventDefault();
  if (busy) return;
  const name = elements.input.value.trim();
  if (!name) return;
  try {
    const result = await request("/api/participants", { name });
    state = result.state;
    elements.input.value = "";
    render();
    elements.input.focus();
    notify(`${result.participant.name} joined the circle.`);
  } catch (error) {
    notify(error.message, true);
  }
}

function openCheckpointModal() {
  if (busy) return;
  if (state.checkpoints.length >= 12) {
    notify("You have reached the 12 checkpoint limit.", true);
    return;
  }
  elements.checkpointName.value = "";
  elements.checkpointModal.hidden = false;
  elements.checkpointName.focus();
}

function closeModal(modal) {
  modal.hidden = true;
}

async function createCheckpoint(event) {
  event.preventDefault();
  try {
    const result = await request("/api/checkpoints", { name: elements.checkpointName.value });
    state = result.state;
    closeModal(elements.checkpointModal);
    render();
    notify(`Checkpoint "${result.name}" saved.`);
  } catch (error) {
    notify(error.message, true);
  }
}

async function restoreCheckpoint(checkpointId) {
  if (busy) return;
  const checkpoint = state.checkpoints.find((item) => item.id === checkpointId);
  if (!checkpoint) return;
  try {
    const result = await request("/api/checkpoints/restore", { checkpoint_id: checkpointId });
    state = result.state;
    render();
    notify(`Checkpoint "${checkpoint.name}" restored.`);
  } catch (error) {
    notify(error.message, true);
  }
}

async function resetRound() {
  try {
    const result = await request("/api/reset", {});
    state = result.state;
    closeModal(elements.confirmModal);
    render();
    notify("A fresh round is ready.");
  } catch (error) {
    notify(error.message, true);
  }
}

document.querySelectorAll(".mode-option").forEach((button) => {
  button.addEventListener("click", () => {
    mode = button.dataset.mode;
    document.querySelectorAll(".mode-option").forEach((option) => {
      option.classList.toggle("selected", option === button);
    });
    elements.spinHint.textContent = mode === "winner"
      ? "One random name will win the draw."
      : "One participant is removed with every spin.";
  });
});
elements.spin.addEventListener("click", spin);
elements.addForm.addEventListener("submit", addParticipant);
elements.checkpointForm.addEventListener("submit", createCheckpoint);
document.querySelector("#checkpoint-button").addEventListener("click", openCheckpointModal);
document.querySelector("#sidebar-save").addEventListener("click", openCheckpointModal);
document.querySelector("#modal-close").addEventListener("click", () => closeModal(elements.checkpointModal));
document.querySelector("#modal-cancel").addEventListener("click", () => closeModal(elements.checkpointModal));
elements.checkpointModal.addEventListener("click", (event) => {
  if (event.target === elements.checkpointModal) closeModal(elements.checkpointModal);
});
elements.checkpoints.addEventListener("click", (event) => {
  const button = event.target.closest("[data-checkpoint-id]");
  if (button) restoreCheckpoint(button.dataset.checkpointId);
});
document.querySelector("#reset-button").addEventListener("click", () => {
  elements.confirmModal.hidden = false;
});
document.querySelector("#confirm-cancel").addEventListener("click", () => closeModal(elements.confirmModal));
document.querySelector("#confirm-reset").addEventListener("click", resetRound);
elements.confirmModal.addEventListener("click", (event) => {
  if (event.target === elements.confirmModal) closeModal(elements.confirmModal);
});
document.addEventListener("keydown", (event) => {
  if (event.code === "Space" && !["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(document.activeElement.tagName)) {
    event.preventDefault();
    spin();
  }
  if (event.key === "Escape") {
    closeModal(elements.checkpointModal);
    closeModal(elements.confirmModal);
  }
});

request("/api/state")
  .then((initialState) => {
    state = initialState;
    render();
  })
  .catch((error) => {
    elements.status.textContent = "Offline";
    elements.statusNote.textContent = "Could not connect to the draw server";
    elements.spin.disabled = true;
    notify(error.message, true);
  });
