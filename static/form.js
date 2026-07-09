let formData = null;

async function loadForm() {
  const res = await fetch("/api/form/data");
  if (res.status === 401) { location.href = "/login"; return; }
  formData = await res.json();

  const meta = document.getElementById("class-meta");
  meta.textContent = `${formData.display_name}${formData.class_tag ? " · " + formData.class_tag : ""}`;

  const container = document.getElementById("modules-container");
  container.innerHTML = "";

  if (formData.modules.length === 0) {
    container.innerHTML = '<div class="empty-state">No form modules have been released yet.<br>Check back soon.</div>';
    return;
  }

  formData.modules.forEach((mod) => {
    const card = document.createElement("div");
    card.className = "module-card";

    const title = document.createElement("div");
    title.className = "module-title";
    title.textContent = mod.week_number ? `Week ${mod.week_number} — ${mod.title}` : mod.title;
    card.appendChild(title);

    (mod.field_defs || []).forEach((field) => {
      const group = document.createElement("div");
      group.className = "field-group";

      const label = document.createElement("label");
      label.htmlFor = `field-${field.key}`;
      label.textContent = field.label;
      group.appendChild(label);

      let input;
      if (field.type === "textarea") {
        input = document.createElement("textarea");
        input.rows = 4;
      } else {
        input = document.createElement("input");
        input.type = "text";
      }
      input.id = `field-${field.key}`;
      input.dataset.key = field.key;
      input.value = formData.answers[field.key] || "";
      input.placeholder = field.placeholder || "";
      input.addEventListener("input", () => {
        document.getElementById("save-status").textContent = "";
        document.getElementById("save-status").className = "save-status";
      });
      group.appendChild(input);
      card.appendChild(group);
    });

    container.appendChild(card);
  });

  updatePreview(formData.system_prompt_preview);
}

function collectAnswers() {
  const answers = {};
  document.querySelectorAll("[data-key]").forEach((el) => {
    answers[el.dataset.key] = el.value;
  });
  return answers;
}

async function saveForm() {
  const answers = collectAnswers();
  const statusEl = document.getElementById("save-status");
  statusEl.textContent = "Saving…";
  statusEl.className = "save-status";

  try {
    const res = await fetch("/api/form/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    });
    if (res.ok) {
      statusEl.textContent = "Saved ✓";
      statusEl.className = "save-status saved";
      // Refresh preview.
      const data = await fetch("/api/form/data").then((r) => r.json());
      updatePreview(data.system_prompt_preview);
    } else {
      statusEl.textContent = "Save failed.";
    }
  } catch (e) {
    statusEl.textContent = "Save failed.";
  }
}

function updatePreview(text) {
  const box = document.getElementById("preview-box");
  box.textContent = text || "(No template configured yet.)";
}

document.getElementById("save-btn").addEventListener("click", saveForm);

document.getElementById("preview-toggle").addEventListener("click", () => {
  const area = document.getElementById("preview-area");
  const toggle = document.getElementById("preview-toggle");
  const hidden = area.classList.toggle("hidden");
  toggle.textContent = (hidden ? "▶" : "▼") + " Preview your agent's system prompt";
});

loadForm();
