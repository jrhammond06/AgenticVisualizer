// ── State ─────────────────────────────────────────────────────────────────────
let allUsers = [];
let allClasses = [];
let allRuleSets = [];
let _loadPackageId = null;
let _loadPackageClassTag = null;

// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "runs") loadRuns();
    if (btn.dataset.tab === "scenarios") loadPackages();
    if (btn.dataset.tab === "students") loadStudents();
  });
});

// ── Utilities ─────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.detail || `Error ${res.status}`);
    throw new Error(err.detail || res.status);
  }
  return res.json();
}

// ── CLASSES (Students tab) ────────────────────────────────────────────────────
async function loadClasses() {
  allClasses = await api("GET", "/api/admin/classes");
  renderClasses();
  populateClassSelects();
}

function renderClasses() {
  const list = document.getElementById("classes-list");
  if (allClasses.length === 0) {
    list.innerHTML = '<div class="empty">No classes yet. Add one above.</div>';
    return;
  }
  list.innerHTML = allClasses.map((c) => `
    <div class="admin-card" style="padding:10px 16px">
      <div class="card-row">
        <span class="badge badge-blue">${esc(c.tag)}</span>
        <span style="font-size:0.875rem">${esc(c.name)}</span>
        <div class="spacer"></div>
        <button class="btn btn-danger" onclick="deleteClass(${c.id}, '${esc(c.tag)}')">Delete</button>
      </div>
    </div>
  `).join("");
}

function populateClassSelects() {
  const opts = '<option value="">— select class —</option>' +
    allClasses.map((c) =>
      `<option value="${esc(c.tag)}">${esc(c.tag)}${c.name ? " — " + esc(c.name) : ""}</option>`
    ).join("");
  ["s-class", "ab-class-filter", "pkg-class-filter", "aa-class-filter"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = opts;
  });
}

async function createClass() {
  const tag = document.getElementById("c-tag").value.trim();
  const name = document.getElementById("c-name").value.trim();
  if (!tag) { alert("Tag is required."); return; }
  await api("POST", "/api/admin/classes", { tag, name });
  document.getElementById("c-tag").value = "";
  document.getElementById("c-name").value = "";
  await loadClasses();
}

async function deleteClass(id, tag) {
  if (!confirm(`Delete class "${tag}"? Students will keep their class_tag value but it will no longer appear in dropdowns.`)) return;
  await api("DELETE", `/api/admin/classes/${id}`);
  await loadClasses();
}

// ── STUDENTS TAB ──────────────────────────────────────────────────────────────
async function loadStudents() {
  allUsers = await api("GET", "/api/admin/users");
  const list = document.getElementById("students-list");
  list.innerHTML = "";
  if (allUsers.length === 0) {
    list.innerHTML = '<div class="empty">No students yet.</div>';
    return;
  }
  allUsers.forEach((u) => {
    const card = document.createElement("div");
    card.className = "admin-card";
    card.innerHTML = `
      <div class="card-row">
        <div class="grow">
          <strong>${esc(u.display_name)}</strong>
          <span style="color:var(--text-muted);margin-left:8px;font-size:0.85rem">@${esc(u.username)}</span>
          <span class="badge badge-blue" style="margin-left:8px">${esc(u.class_tag) || "no class"}</span>
        </div>
        <button class="btn btn-primary" onclick="openStudentAgentModal(${u.id}, '${esc(u.display_name)}', '${esc(u.class_tag)}')">Agent →</button>
        <button class="btn btn-secondary" onclick="editStudent(${u.id})">Edit</button>
        <button class="btn btn-danger" onclick="deleteStudent(${u.id}, '${esc(u.display_name)}')">Delete</button>
      </div>
      <div id="edit-student-${u.id}" class="hidden" style="margin-top:12px">
        <div class="form-row cols-3">
          <div><span class="field-label">Display name</span>
               <input class="admin-input" id="edit-name-${u.id}" value="${esc(u.display_name)}"></div>
          <div><span class="field-label">Class</span>
               <select class="admin-select" id="edit-class-${u.id}" style="width:100%">
                 ${allClasses.map((c) => `<option value="${esc(c.tag)}" ${c.tag === u.class_tag ? "selected" : ""}>${esc(c.tag)}${c.name ? " — " + esc(c.name) : ""}</option>`).join("")}
               </select></div>
          <div><span class="field-label">New password (leave blank to keep)</span>
               <input class="admin-input" id="edit-pass-${u.id}" type="password" placeholder="unchanged"></div>
        </div>
        <button class="btn btn-primary" onclick="saveStudent(${u.id})">Save</button>
      </div>
    `;
    list.appendChild(card);
  });
}

function editStudent(id) {
  const el = document.getElementById(`edit-student-${id}`);
  el.classList.toggle("hidden");
}

async function saveStudent(id) {
  await api("PUT", `/api/admin/users/${id}`, {
    display_name: document.getElementById(`edit-name-${id}`).value,
    class_tag: document.getElementById(`edit-class-${id}`).value,
    password: document.getElementById(`edit-pass-${id}`).value,
  });
  loadStudents();
}

async function createStudent() {
  const username = document.getElementById("s-username").value.trim();
  const display_name = document.getElementById("s-name").value.trim();
  const class_tag = document.getElementById("s-class").value.trim();
  const password = document.getElementById("s-password").value;
  if (!username) { alert("Username is required."); return; }
  await api("POST", "/api/admin/users", { username, display_name: display_name || username, class_tag, password });
  ["s-username", "s-name", "s-class", "s-password"].forEach((id) => { document.getElementById(id).value = ""; });
  loadStudents();
}

async function deleteStudent(id, name) {
  if (!confirm(`Delete student "${name}"? This cannot be undone.`)) return;
  await api("DELETE", `/api/admin/users/${id}`);
  loadStudents();
}

// ── Field key palette ─────────────────────────────────────────────────────────
let _tmplSelStart = 0, _tmplSelEnd = 0;

function _setupTemplateCursorTracking() {
  const ta = document.getElementById("template-text");
  if (ta._cursorTracked) return;
  ta._cursorTracked = true;
  ta.addEventListener("blur", () => {
    _tmplSelStart = ta.selectionStart;
    _tmplSelEnd = ta.selectionEnd;
  });
}

function renderFieldKeyPalette(modules) {
  _setupTemplateCursorTracking();
  const container = document.getElementById("field-key-palette");
  const chips = [{ key: "display_name", label: "Student name", builtin: true }];
  modules.forEach((mod) => {
    const fields = Array.isArray(mod.field_defs) ? mod.field_defs : JSON.parse(mod.field_defs || "[]");
    fields.forEach((f) => chips.push({ key: f.key, label: f.label, module: mod.title }));
  });

  container.innerHTML = "";
  if (chips.length === 1 && modules.length === 0) {
    const hint = document.createElement("span");
    hint.className = "hint";
    hint.textContent = "Add modules with fields and they'll appear here.";
    container.appendChild(hint);
  }

  chips.forEach((chip) => {
    const el = document.createElement("span");
    el.className = "field-chip" + (chip.builtin ? " field-chip-builtin" : "");
    el.textContent = `{${chip.key}}`;
    el.title = chip.module ? `${chip.module}: ${chip.label}` : chip.label;
    el.draggable = true;
    el.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", `{${chip.key}}`);
      e.dataTransfer.effectAllowed = "copy";
    });
    el.addEventListener("click", () => insertFieldKey(chip.key));
    container.appendChild(el);
  });
}

function insertFieldKey(key) {
  const ta = document.getElementById("template-text");
  const token = `{${key}}`;
  const start = ta === document.activeElement ? ta.selectionStart : _tmplSelStart;
  const end   = ta === document.activeElement ? ta.selectionEnd   : _tmplSelEnd;
  ta.value = ta.value.slice(0, start) + token + ta.value.slice(end);
  const newPos = start + token.length;
  ta.focus();
  ta.setSelectionRange(newPos, newPos);
  _tmplSelStart = _tmplSelEnd = newPos;
}

// ── AGENT BUILDER MODAL (form modules + prompt template) ──────────────────────
function openAgentBuilderModal() {
  document.getElementById("agent-builder-modal").classList.remove("hidden");
  if (document.getElementById("ab-class-filter").value.trim()) {
    loadFormTab();
  } else {
    document.getElementById("modules-list").innerHTML = '<div class="empty">Select a class above to manage its questions.</div>';
    document.getElementById("template-text").value = "";
    document.getElementById("field-key-palette").innerHTML = "";
    document.getElementById("completion-tracker").innerHTML = "";
  }
}

function closeAgentBuilderModal() {
  document.getElementById("agent-builder-modal").classList.add("hidden");
}

async function loadFormTab() {
  const classTag = document.getElementById("ab-class-filter").value.trim();
  const [modules, tmpl] = await Promise.all([
    api("GET", `/api/admin/modules?class_tag=${encodeURIComponent(classTag)}`),
    api("GET", `/api/admin/template?class_tag=${encodeURIComponent(classTag)}`),
  ]);

  document.getElementById("template-text").value = tmpl.template || "";
  renderModulesList(modules, classTag);
  renderFieldKeyPalette(modules);
  loadCompletionTracker(classTag, modules);
}

function renderModulesList(modules, classTag) {
  const list = document.getElementById("modules-list");
  list.innerHTML = "";
  if (modules.length === 0) {
    list.innerHTML = '<div class="empty">No modules for this class yet.</div>';
    return;
  }
  modules.forEach((mod) => {
    const card = document.createElement("div");
    card.className = "admin-card";
    const lockedBadge = mod.unlocked
      ? '<span class="badge badge-green">Unlocked</span>'
      : '<span class="badge badge-gray">Locked</span>';
    card.innerHTML = `
      <div class="card-row">
        <strong>${esc(mod.title)}</strong>
        <span class="badge badge-blue">Week ${mod.week_number}</span>
        ${lockedBadge}
        <div class="spacer"></div>
        <button class="btn btn-secondary" onclick="toggleModuleEdit('mod-${mod.id}')">Edit</button>
        <button class="btn btn-danger" onclick="deleteModule(${mod.id})">✕</button>
      </div>
      <div id="mod-${mod.id}" class="hidden" style="margin-top:12px">
        <div class="form-row cols-2">
          <div><span class="field-label">Title</span>
               <input class="admin-input" id="mod-title-${mod.id}" value="${esc(mod.title)}"></div>
          <div><span class="field-label">Week number</span>
               <input class="admin-input" type="number" id="mod-week-${mod.id}" value="${mod.week_number}"></div>
        </div>
        <div style="margin-bottom:12px">
          <span class="field-label">Preamble <span style="font-weight:400;color:var(--text-muted)">(shown to students above the fields)</span></span>
          <textarea class="admin-textarea" id="mod-preamble-${mod.id}" style="min-height:72px">${esc(mod.preamble || "")}</textarea>
        </div>
        <label style="display:flex;align-items:center;gap:8px;margin-bottom:12px;font-size:0.875rem;font-weight:600">
          <input type="checkbox" id="mod-unlocked-${mod.id}" ${mod.unlocked ? "checked" : ""}> Unlocked (visible to students)
        </label>
        <div class="section-title">Fields</div>
        <div id="fields-${mod.id}"></div>
        <button class="btn btn-secondary" style="margin-bottom:12px" onclick="addField(${mod.id})">+ Add field</button>
        <br>
        <button class="btn btn-primary" onclick="saveModule(${mod.id})">Save module</button>
      </div>
    `;
    list.appendChild(card);
    renderFieldDefs(mod.id, mod.field_defs || []);
  });
}

function toggleModuleEdit(id) {
  document.getElementById(id).classList.toggle("hidden");
}

// ── Field store (replaces live-DOM field editing) ─────────────────────────────
const _moduleFields = {};
let _editingField = null;

function renderFieldDefs(modId, fields) {
  _moduleFields[modId] = fields.map((f) => ({ key: f.key, label: f.label }));
  _renderFieldRows(modId);
}

function _renderFieldRows(modId) {
  const container = document.getElementById(`fields-${modId}`);
  container.innerHTML = "";
  const fields = _moduleFields[modId] || [];
  if (fields.length === 0) {
    container.innerHTML = '<div class="hint" style="padding:4px 0 8px">No fields yet.</div>';
    return;
  }
  fields.forEach((f, idx) => {
    const row = document.createElement("div");
    row.className = "field-row";
    row.innerHTML = `
      <span class="field-row-key">{${esc(f.key || "…")}}</span>
      <span class="field-row-label">${esc(f.label || "")}</span>
      <button class="btn btn-secondary" onclick="openFieldModal(${modId}, ${idx})">Edit</button>
      <button class="btn btn-danger" onclick="removeField(${modId}, ${idx})">✕</button>
    `;
    container.appendChild(row);
  });
}

function getFieldDefs(modId) {
  return (_moduleFields[modId] || []).filter((f) => f.key);
}

function addField(modId) {
  if (!_moduleFields[modId]) _moduleFields[modId] = [];
  const idx = _moduleFields[modId].length;
  _moduleFields[modId].push({ key: "", label: "" });
  _renderFieldRows(modId);
  openFieldModal(modId, idx, true);
}

function removeField(modId, idx) {
  (_moduleFields[modId] || []).splice(idx, 1);
  _renderFieldRows(modId);
}

function openFieldModal(modId, idx, isNew = false) {
  const f = (_moduleFields[modId] || [])[idx] || { key: "", label: "" };
  _editingField = { modId, idx, isNew };
  document.getElementById("field-modal-title").textContent = isNew ? "New field" : "Edit field";
  document.getElementById("field-modal-key").value = f.key;
  document.getElementById("field-modal-label").value = f.label;
  document.getElementById("field-modal").classList.remove("hidden");
  setTimeout(() => document.getElementById("field-modal-key").focus(), 50);
}

function saveFieldModal() {
  const { modId, idx } = _editingField;
  const key = document.getElementById("field-modal-key").value.trim().replace(/\s+/g, "_");
  const label = document.getElementById("field-modal-label").value.trim();
  if (!key) { alert("Key is required."); return; }
  _moduleFields[modId][idx] = { key, label: label || key };
  _renderFieldRows(modId);
  closeFieldModal();
}

function closeFieldModal() {
  const { modId, idx, isNew } = _editingField || {};
  if (isNew && _moduleFields[modId]?.[idx]?.key === "") {
    _moduleFields[modId].splice(idx, 1);
    _renderFieldRows(modId);
  }
  document.getElementById("field-modal").classList.add("hidden");
  _editingField = null;
}

async function saveModule(modId) {
  await api("PUT", `/api/admin/modules/${modId}`, {
    title: document.getElementById(`mod-title-${modId}`).value.trim(),
    week_number: parseInt(document.getElementById(`mod-week-${modId}`).value, 10) || 0,
    preamble: document.getElementById(`mod-preamble-${modId}`).value,
    unlocked: document.getElementById(`mod-unlocked-${modId}`).checked,
    field_defs: getFieldDefs(modId),
  });
  loadFormTab();
}

async function deleteModule(modId) {
  if (!confirm("Delete this module?")) return;
  await api("DELETE", `/api/admin/modules/${modId}`);
  loadFormTab();
}

async function createModule() {
  const classTag = document.getElementById("ab-class-filter").value.trim();
  if (!classTag) { alert("Select a class first."); return; }
  await api("POST", "/api/admin/modules", {
    class_tag: classTag, title: "New module", week_number: 0, field_defs: [], unlocked: false,
  });
  loadFormTab();
}

async function saveTemplate() {
  const classTag = document.getElementById("ab-class-filter").value.trim();
  if (!classTag) { alert("Select a class first."); return; }
  await api("PUT", "/api/admin/template", {
    class_tag: classTag,
    template: document.getElementById("template-text").value,
  });
  const status = document.getElementById("template-status");
  status.textContent = "Saved ✓";
  setTimeout(() => { status.textContent = ""; }, 2000);
}

async function loadCompletionTracker(classTag, modules) {
  const container = document.getElementById("completion-tracker");
  if (!classTag || modules.length === 0) {
    container.innerHTML = "";
    return;
  }
  const profiles = await api("GET", `/api/admin/profiles?class_tag=${encodeURIComponent(classTag)}`);
  if (profiles.length === 0) {
    container.innerHTML = '<div class="empty">No students in this class.</div>';
    return;
  }

  const headerCells = modules.map((m) => `<th>${esc(m.title)}</th>`).join("");
  const rows = profiles.map((p) => {
    const cells = modules.map((m) => {
      const fields = Array.isArray(m.field_defs) ? m.field_defs : JSON.parse(m.field_defs || "[]");
      const filled = fields.filter((f) => {
        const ans = (p.answers || {})[f.key];
        return ans && ans.trim() !== "";
      }).length;
      const total = fields.length;
      if (total === 0) return `<td><span class="badge badge-gray">—</span></td>`;
      const cls = filled === 0 ? "badge-gray" : filled < total ? "badge-yellow" : "badge-green";
      return `<td><span class="badge ${cls}">${filled}/${total}</span></td>`;
    }).join("");
    return `<tr><td><strong>${esc(p.display_name)}</strong></td>${cells}</tr>`;
  }).join("");

  container.innerHTML = `
    <div class="section-title" style="margin-top:24px">Completion</div>
    <div class="admin-card" style="padding:0;overflow-x:auto">
      <table class="completion-table">
        <thead><tr><th>Student</th>${headerCells}</tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// ── RULE SET LIBRARY MODAL ─────────────────────────────────────────────────────
function openRuleSetsModal() {
  document.getElementById("rulesets-modal").classList.remove("hidden");
  loadRuleSets();
}

function closeRuleSetsModal() {
  document.getElementById("rulesets-modal").classList.add("hidden");
  loadPackages(); // refresh rule-set names shown in scenario cards
}

async function loadRuleSets() {
  allRuleSets = await api("GET", "/api/admin/rulesets");
  renderRuleSets();
}

function renderRuleSets() {
  const list = document.getElementById("rulesets-list");
  list.innerHTML = "";
  if (allRuleSets.length === 0) {
    list.innerHTML = '<div class="empty">No rule sets yet.</div>';
    return;
  }
  allRuleSets.forEach((rs) => {
    const card = document.createElement("div");
    card.className = "admin-card";
    card.innerHTML = `
      <div class="card-row">
        <strong>${esc(rs.name)}</strong>
        <span class="badge badge-blue">${rs.rules.length} rules</span>
        <div class="spacer"></div>
        <button class="btn btn-secondary" onclick="toggleRsEdit('rs-${rs.id}')">Edit</button>
        <button class="btn btn-danger" onclick="deleteRuleSet(${rs.id})">Delete</button>
      </div>
      <div id="rs-${rs.id}" class="hidden" style="margin-top:12px">
        <div class="form-row cols-2">
          <div><span class="field-label">Name</span>
               <input class="admin-input" id="rs-name-${rs.id}" value="${esc(rs.name)}"></div>
          <div><span class="field-label">Description</span>
               <input class="admin-input" id="rs-desc-${rs.id}" value="${esc(rs.description)}"></div>
        </div>
        <div class="section-title">Rules</div>
        <div id="rs-rules-${rs.id}"></div>
        <button class="btn btn-secondary" style="margin-bottom:12px" onclick="addRuleToSet(${rs.id})">+ Add rule</button>
        <div class="section-title" style="margin-top:16px">Agent speaking instructions</div>
        <p class="hint" style="margin-top:0">Replaces the default speaking-rules block injected into every agent's system prompt. Leave blank to use built-in defaults.</p>
        <textarea class="admin-textarea" id="rs-instructions-${rs.id}" style="min-height:120px;margin-bottom:12px">${esc(rs.agent_instructions || "")}</textarea>
        <br>
        <button class="btn btn-primary" onclick="saveRuleSet(${rs.id})">Save</button>
      </div>
    `;
    list.appendChild(card);
    renderRuleItems(rs.id, rs.rules);
  });
}

function toggleRsEdit(id) {
  document.getElementById(id).classList.toggle("hidden");
}

function _appliesToSelect(idx, value) {
  const val = value || "referee";
  return `
    <select class="admin-select" data-idx="${idx}" data-prop="applies_to" style="align-self:start" title="Who receives this rule">
      <option value="both"      ${val === "both"     ? "selected" : ""}>Agents + Referee</option>
      <option value="referee"   ${val === "referee"  ? "selected" : ""}>Referee only</option>
      <option value="agents"    ${val === "agents"   ? "selected" : ""}>Agents only</option>
    </select>`;
}

function renderRuleItems(rsId, rules) {
  const container = document.getElementById(`rs-rules-${rsId}`);
  container.innerHTML = "";
  rules.forEach((r, idx) => {
    const row = document.createElement("div");
    row.className = "rule-item";
    row.innerHTML = `
      <div class="rule-item-fields">
        <input class="admin-input" placeholder="Rule name" value="${esc(r.name)}" data-idx="${idx}" data-prop="name">
        <textarea class="admin-textarea" placeholder="Rule text" data-idx="${idx}" data-prop="text">${esc(r.text)}</textarea>
      </div>
      <select class="admin-select" data-idx="${idx}" data-prop="severity" style="align-self:start">
        <option value="hard_constraint" ${r.severity === "hard_constraint" ? "selected" : ""}>Hard constraint</option>
        <option value="guideline"       ${r.severity === "guideline"       ? "selected" : ""}>Guideline</option>
      </select>
      ${_appliesToSelect(idx, r.applies_to)}
      <button class="btn btn-danger" style="align-self:start" onclick="removeRuleItem(${rsId},${idx})">✕</button>
    `;
    container.appendChild(row);
  });
}

function addRuleToSet(rsId) {
  const container = document.getElementById(`rs-rules-${rsId}`);
  const idx = container.querySelectorAll(".rule-item").length;
  const row = document.createElement("div");
  row.className = "rule-item";
  row.innerHTML = `
    <div class="rule-item-fields">
      <input class="admin-input" placeholder="Rule name" data-idx="${idx}" data-prop="name">
      <textarea class="admin-textarea" placeholder="Rule text" data-idx="${idx}" data-prop="text"></textarea>
    </div>
    <select class="admin-select" data-idx="${idx}" data-prop="severity" style="align-self:start">
      <option value="hard_constraint">Hard constraint</option>
      <option value="guideline" selected>Guideline</option>
    </select>
    ${_appliesToSelect(idx, "both")}
    <button class="btn btn-danger" style="align-self:start" onclick="removeRuleItem(${rsId},${idx})">✕</button>
  `;
  container.appendChild(row);
}

function removeRuleItem(rsId, idx) {
  const items = document.querySelectorAll(`#rs-rules-${rsId} .rule-item`);
  if (items[idx]) items[idx].remove();
}

function getRuleItems(rsId) {
  const items = document.querySelectorAll(`#rs-rules-${rsId} .rule-item`);
  const rules = [];
  items.forEach((item) => {
    const name = item.querySelector('[data-prop="name"]').value.trim();
    const text = item.querySelector('[data-prop="text"]').value.trim();
    const severity = item.querySelector('[data-prop="severity"]').value;
    const applies_to = item.querySelector('[data-prop="applies_to"]').value;
    if (name || text) rules.push({ name: name || "Unnamed", text, severity, applies_to });
  });
  return rules;
}

async function saveRuleSet(rsId) {
  await api("PUT", `/api/admin/rulesets/${rsId}`, {
    name: document.getElementById(`rs-name-${rsId}`).value,
    description: document.getElementById(`rs-desc-${rsId}`).value,
    rules: getRuleItems(rsId),
    agent_instructions: document.getElementById(`rs-instructions-${rsId}`).value,
  });
  loadRuleSets();
}

async function createRuleSet() {
  await api("POST", "/api/admin/rulesets", { name: "New rule set", rules: [] });
  loadRuleSets();
}

async function deleteRuleSet(rsId) {
  if (!confirm("Delete this rule set?")) return;
  await api("DELETE", `/api/admin/rulesets/${rsId}`);
  loadRuleSets();
}

// ── SCENARIOS TAB (packages: topic + goal + hard constraints + rule set) ──────
async function loadPackages() {
  const classTag = document.getElementById("pkg-class-filter").value.trim();
  const [packages, rulesets] = await Promise.all([
    api("GET", `/api/admin/packages?class_tag=${encodeURIComponent(classTag)}`),
    api("GET", "/api/admin/rulesets"),
  ]);
  allRuleSets = rulesets;
  const list = document.getElementById("packages-list");
  list.innerHTML = "";
  if (packages.length === 0) {
    list.innerHTML = '<div class="empty">No packages yet.</div>';
    return;
  }
  packages.forEach((pkg) => {
    const rsName = allRuleSets.find((r) => r.id === pkg.rule_set_id)?.name || "None";
    const card = document.createElement("div");
    card.className = "admin-card";
    card.innerHTML = `
      <div class="card-row">
        <div>
          <strong>${esc(pkg.name)}</strong>
          <span class="badge badge-blue" style="margin-left:8px">${esc(pkg.class_tag) || "no class"}</span>
        </div>
        <div class="spacer"></div>
        <button class="btn btn-success" onclick="openLoadModal(${pkg.id}, '${esc(pkg.name)}', '${esc(pkg.class_tag)}')">Load for Session →</button>
        <button class="btn btn-secondary" onclick="togglePkgEdit('pkg-${pkg.id}')">Edit</button>
        <button class="btn btn-danger" onclick="deletePackage(${pkg.id})">Delete</button>
      </div>
      <div style="color:var(--text-muted);font-size:0.85rem;margin-top:4px">${esc(pkg.topic)}</div>
      ${pkg.goal ? `<div style="color:var(--text-muted);font-size:0.8rem;margin-top:2px">🎯 ${esc(pkg.goal)}</div>` : ""}
      <div id="pkg-${pkg.id}" class="hidden" style="margin-top:12px">
        <div class="form-row cols-2">
          <div><span class="field-label">Scenario name</span>
               <input class="admin-input" id="pkg-name-${pkg.id}" value="${esc(pkg.name)}"></div>
          <div><span class="field-label">Rule set (ground rules)</span>
               <div style="display:flex;gap:6px">
                 <select class="admin-select grow" id="pkg-rs-${pkg.id}" style="width:100%">
                   <option value="">None</option>
                   ${allRuleSets.map((r) => `<option value="${r.id}" ${r.id === pkg.rule_set_id ? "selected" : ""}>${esc(r.name)}</option>`).join("")}
                 </select>
                 <button class="btn btn-secondary" onclick="openRuleSetsModal()" title="Create, edit, or delete rule sets" style="white-space:nowrap">⚙ Manage</button>
               </div></div>
        </div>
        <div style="margin-bottom:12px">
          <span class="field-label">Topic / core question</span>
          <input class="admin-input" id="pkg-topic-${pkg.id}" value="${esc(pkg.topic)}">
        </div>
        <div style="margin-bottom:12px">
          <span class="field-label">Goal <span style="font-weight:400;color:var(--text-muted)">(what a successful outcome looks like — shown to the Referee)</span></span>
          <textarea class="admin-textarea" id="pkg-goal-${pkg.id}" style="min-height:60px">${esc(pkg.goal || "")}</textarea>
        </div>
        <div class="section-title">Hard constraints (issue-specific)</div>
        <div id="pkg-constraints-${pkg.id}"></div>
        <button class="btn btn-secondary" style="margin-bottom:12px" onclick="addConstraint(${pkg.id})">+ Add constraint</button>
        <div class="section-title" style="margin-top:16px">Agent identity template</div>
        <p class="hint" style="margin-top:0">Defines who agents are in this scenario. Available placeholders: <code>{name}</code>, <code>{goal}</code>, <code>{topic}</code>, <code>{rules}</code>, <code>{system_prompt}</code>, <code>{speaking_instructions}</code>. Leave blank to use built-in defaults.</p>
        <textarea class="admin-textarea" id="pkg-template-${pkg.id}" style="min-height:180px;font-family:monospace;font-size:0.8rem;margin-bottom:12px">${esc(pkg.agent_prompt_template || "")}</textarea>
        <br>
        <button class="btn btn-primary" onclick="savePackage(${pkg.id})">Save</button>
      </div>
    `;
    list.appendChild(card);
    renderConstraints(pkg.id, pkg.constraints || []);
  });
}

function togglePkgEdit(id) {
  document.getElementById(id).classList.toggle("hidden");
}

function renderConstraints(pkgId, constraints) {
  const container = document.getElementById(`pkg-constraints-${pkgId}`);
  container.innerHTML = "";
  constraints.forEach((c, idx) => {
    const row = document.createElement("div");
    row.className = "rule-item";
    row.innerHTML = `
      <div class="rule-item-fields">
        <input class="admin-input" placeholder="Name" value="${esc(c.name)}" data-idx="${idx}" data-prop="name">
        <textarea class="admin-textarea" placeholder="Constraint text" data-idx="${idx}" data-prop="text">${esc(c.text)}</textarea>
      </div>
      <div style="align-self:start;font-size:0.75rem;font-weight:700;color:#991b1b;padding:4px 0">HARD</div>
      <button class="btn btn-danger" style="align-self:start" onclick="removeConstraint(${pkgId},${idx})">✕</button>
    `;
    container.appendChild(row);
  });
}

function addConstraint(pkgId) {
  const container = document.getElementById(`pkg-constraints-${pkgId}`);
  const idx = container.querySelectorAll(".rule-item").length;
  const row = document.createElement("div");
  row.className = "rule-item";
  row.innerHTML = `
    <div class="rule-item-fields">
      <input class="admin-input" placeholder="Name" data-idx="${idx}" data-prop="name">
      <textarea class="admin-textarea" placeholder="Constraint text" data-idx="${idx}" data-prop="text"></textarea>
    </div>
    <div style="align-self:start;font-size:0.75rem;font-weight:700;color:#991b1b;padding:4px 0">HARD</div>
    <button class="btn btn-danger" style="align-self:start" onclick="removeConstraint(${pkgId},${idx})">✕</button>
  `;
  container.appendChild(row);
}

function removeConstraint(pkgId, idx) {
  const items = document.querySelectorAll(`#pkg-constraints-${pkgId} .rule-item`);
  if (items[idx]) items[idx].remove();
}

function getConstraints(pkgId) {
  const items = document.querySelectorAll(`#pkg-constraints-${pkgId} .rule-item`);
  const result = [];
  items.forEach((item) => {
    const name = item.querySelector('[data-prop="name"]').value.trim();
    const text = item.querySelector('[data-prop="text"]').value.trim();
    if (name || text) result.push({ name: name || "Unnamed", text, severity: "hard_constraint" });
  });
  return result;
}

async function savePackage(pkgId) {
  const rsVal = document.getElementById(`pkg-rs-${pkgId}`).value;
  await api("PUT", `/api/admin/packages/${pkgId}`, {
    name: document.getElementById(`pkg-name-${pkgId}`).value,
    topic: document.getElementById(`pkg-topic-${pkgId}`).value,
    goal: document.getElementById(`pkg-goal-${pkgId}`).value,
    rule_set_id: rsVal ? parseInt(rsVal, 10) : null,
    constraints: getConstraints(pkgId),
    agent_prompt_template: document.getElementById(`pkg-template-${pkgId}`).value,
  });
  loadPackages();
}

async function createPackage() {
  const classTag = document.getElementById("pkg-class-filter").value.trim();
  await api("POST", "/api/admin/packages", {
    class_tag: classTag, name: "New package", topic: "", constraints: [],
  });
  loadPackages();
}

async function deletePackage(pkgId) {
  if (!confirm("Delete this package?")) return;
  await api("DELETE", `/api/admin/packages/${pkgId}`);
  loadPackages();
}

// ── Load package modal ────────────────────────────────────────────────────────
function openLoadModal(pkgId, pkgName, classTag) {
  _loadPackageId = pkgId;
  _loadPackageClassTag = classTag;
  document.getElementById("load-modal-title").textContent = `Load: ${pkgName}`;

  const studentList = document.getElementById("load-student-list");
  const students = allUsers.filter((u) => !classTag || u.class_tag === classTag);
  studentList.innerHTML = students.length === 0
    ? '<div class="empty">No students found for this class tag.</div>'
    : students.map((u) => `
        <div class="student-check">
          <input type="checkbox" id="sc-${u.id}" value="${u.id}" checked>
          <label for="sc-${u.id}">${esc(u.display_name)} <span style="color:var(--text-muted)">@${esc(u.username)}</span></label>
        </div>
      `).join("");

  document.getElementById("load-modal").classList.remove("hidden");
}

function closeLoadModal() {
  document.getElementById("load-modal").classList.add("hidden");
  _loadPackageId = null;
}

async function confirmLoad() {
  const checked = [...document.querySelectorAll('#load-student-list input[type=checkbox]:checked')];
  const student_ids = checked.map((c) => parseInt(c.value, 10));
  await api("POST", `/api/admin/packages/${_loadPackageId}/load`, { student_ids });
  closeLoadModal();
  window.location.href = "/session";
}

// ── STUDENT AGENT MODAL (form answers + generated/overridden system prompt) ───
async function openStudentAgentModal(userId, displayName, classTag) {
  document.getElementById("sa-modal-title").textContent = `${displayName}'s agent`;
  document.getElementById("student-agent-modal").dataset.userId = userId;
  const body = document.getElementById("sa-modal-body");
  body.innerHTML = '<div class="empty">Loading…</div>';
  document.getElementById("student-agent-modal").classList.remove("hidden");

  if (!classTag) {
    body.innerHTML = '<div class="empty">This student has no class assigned yet, so no agent-builder form applies.</div>';
    return;
  }
  const profiles = await api("GET", `/api/admin/profiles?class_tag=${encodeURIComponent(classTag)}`);
  const p = profiles.find((pr) => pr.user_id === userId);
  if (!p) {
    body.innerHTML = '<div class="empty">No profile data found.</div>';
    return;
  }
  renderStudentAgentBody(p);
}

// Shared by the single-student modal and the all-agents bulk view.
function _agentPanelHtml(p) {
  const isOverridden = p.system_prompt_override !== null && p.system_prompt_override !== undefined;
  const promptText = isOverridden ? p.system_prompt_override : (p.system_prompt || "");
  const statusBadge = isOverridden
    ? '<span class="badge badge-yellow">Overridden</span>'
    : '<span class="badge badge-gray">From template</span>';

  const answerEntries = Object.entries(p.answers || {});
  const answersHtml = answerEntries.length > 0
    ? answerEntries.map(([k, v]) =>
        `<div style="margin-bottom:8px">
           <div style="font-family:monospace;font-size:0.78rem;color:var(--primary);margin-bottom:2px">${esc(k)}</div>
           <div style="font-size:0.85rem;white-space:pre-wrap">${esc(v)}</div>
         </div>`
      ).join("")
    : '<span class="hint">No form answers saved yet.</span>';

  const updatedText = p.last_updated
    ? `Saved ${new Date(p.last_updated).toLocaleString()}`
    : "Not submitted yet";

  return `
    <div class="card-row" style="margin-bottom:12px">
      ${statusBadge}
      <span class="hint" style="margin-left:auto">${esc(updatedText)}</span>
    </div>
    <div class="section-title">Form answers</div>
    <div style="background:var(--bg);border-radius:8px;padding:12px;line-height:1.6;margin-bottom:16px">
      ${answersHtml}
    </div>
    <div class="section-title">System prompt ${isOverridden ? "(override active)" : "(template-rendered)"}</div>
    <div class="card-row" style="margin-bottom:8px">
      <span class="hint" style="font-size:0.75rem">${p.system_prompt ? "" : "⚠ No template configured for this class."}</span>
      <div class="spacer"></div>
      <button class="btn btn-secondary" onclick="resetPromptOverride(${p.user_id})">Reset</button>
      <button class="btn btn-primary" onclick="savePromptOverride(${p.user_id})">Save override</button>
    </div>
    <textarea class="admin-textarea" id="prompt-override-${p.user_id}"
      style="min-height:200px;font-family:monospace;font-size:0.8rem">${esc(promptText)}</textarea>
  `;
}

function renderStudentAgentBody(p) {
  document.getElementById("sa-modal-body").innerHTML = _agentPanelHtml(p);
}

function closeStudentAgentModal() {
  document.getElementById("student-agent-modal").classList.add("hidden");
}

// ── ALL AGENTS MODAL (whole-class overview: every student's answers + prompt) ─
function openAllAgentsModal() {
  document.getElementById("all-agents-modal").classList.remove("hidden");
  if (document.getElementById("aa-class-filter").value.trim()) {
    loadAllAgents();
  } else {
    document.getElementById("all-agents-list").innerHTML = '<div class="empty">Select a class above to view all agents.</div>';
  }
}

function closeAllAgentsModal() {
  document.getElementById("all-agents-modal").classList.add("hidden");
}

async function loadAllAgents() {
  const classTag = document.getElementById("aa-class-filter").value.trim();
  const list = document.getElementById("all-agents-list");
  if (!classTag) {
    list.innerHTML = '<div class="empty">Select a class above to view all agents.</div>';
    return;
  }
  const profiles = await api("GET", `/api/admin/profiles?class_tag=${encodeURIComponent(classTag)}`);
  list.innerHTML = "";
  if (profiles.length === 0) {
    list.innerHTML = '<div class="empty">No students found.</div>';
    return;
  }
  profiles.forEach((p) => {
    const card = document.createElement("div");
    card.className = "admin-card";
    card.innerHTML = `
      <div class="card-row" style="margin-bottom:4px">
        <strong>${esc(p.display_name)}</strong>
      </div>
      ${_agentPanelHtml(p)}
    `;
    list.appendChild(card);
  });
}

function _refreshAgentViews(userId) {
  const saModal = document.getElementById("student-agent-modal");
  if (!saModal.classList.contains("hidden") && parseInt(saModal.dataset.userId, 10) === userId) {
    refreshStudentAgentModal(userId);
  }
  if (!document.getElementById("all-agents-modal").classList.contains("hidden")) {
    loadAllAgents();
  }
}

async function savePromptOverride(userId) {
  const text = document.getElementById(`prompt-override-${userId}`).value;
  await api("PUT", `/api/admin/profiles/${userId}/prompt`, { system_prompt_override: text });
  _refreshAgentViews(userId);
}

async function resetPromptOverride(userId) {
  if (!confirm("Remove the override and revert to the template-derived prompt?")) return;
  await api("PUT", `/api/admin/profiles/${userId}/prompt`, { system_prompt_override: null });
  _refreshAgentViews(userId);
}

function refreshStudentAgentModal(userId) {
  const u = allUsers.find((x) => x.id === userId);
  if (!u) return;
  openStudentAgentModal(userId, u.display_name, u.class_tag);
}

// ── RUNS TAB ──────────────────────────────────────────────────────────────────
async function loadRuns() {
  const runs = await api("GET", "/api/admin/runs");
  const list = document.getElementById("runs-list");
  list.innerHTML = "";
  if (runs.length === 0) {
    list.innerHTML = '<div class="empty">No runs recorded yet.</div>';
    return;
  }
  runs.forEach((r) => {
    const row = document.createElement("div");
    row.className = "run-row";
    const started = new Date(r.started_at).toLocaleString();
    const outcome = r.consensus_reached
      ? '<span class="badge badge-green">Consensus</span>'
      : '<span class="badge badge-yellow">No consensus</span>';
    row.innerHTML = `
      <div>
        <strong>${esc(r.package_name || "Unknown package")}</strong>
        <div class="run-meta">${started} · class: ${esc(r.class_tag) || "—"}</div>
      </div>
      ${outcome}
      <div style="font-size:0.85rem;color:var(--text-muted);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        ${esc(r.outcome_summary || "—")}
      </div>
      <button class="btn btn-secondary" onclick="downloadTrace(${r.id})">⬇ Trace</button>
    `;
    list.appendChild(row);
  });
}

async function downloadTrace(runId) {
  const trace = await api("GET", `/api/admin/runs/${runId}/trace`);
  const blob = new Blob([JSON.stringify(trace, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `run-${runId}-trace.json`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Init ──────────────────────────────────────────────────────────────────────
(async () => {
  await loadClasses();
  loadStudents();
})();
