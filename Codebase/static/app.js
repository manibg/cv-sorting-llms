(() => {
  "use strict";

  const state = {
    cvFiles: [],
    jdFile: null,
    jdMode: "paste",
    lastResult: null,
  };

  const els = {
    form: document.getElementById("rankForm"),
    cvInput: document.getElementById("cvInput"),
    cvDropzone: document.getElementById("cvDropzone"),
    cvList: document.getElementById("cvList"),
    jdText: document.getElementById("jdText"),
    jdInput: document.getElementById("jdInput"),
    jdDropzone: document.getElementById("jdDropzone"),
    jdFileName: document.getElementById("jdFileName"),
    skillsInput: document.getElementById("skillsInput"),
    skillChips: document.getElementById("skillChips"),
    mockToggle: document.getElementById("mockToggle"),
    runBtn: document.getElementById("runBtn"),
    sampleBtn: document.getElementById("sampleBtn"),
    resetBtn: document.getElementById("resetBtn"),
    exportBtn: document.getElementById("exportBtn"),
    helpBtn: document.getElementById("helpBtn"),
    helpPanel: document.getElementById("helpPanel"),
    statusPill: document.getElementById("statusPill"),
    formError: document.getElementById("formError"),
    emptyState: document.getElementById("emptyState"),
    progressState: document.getElementById("progressState"),
    progressText: document.getElementById("progressText"),
    resultsBody: document.getElementById("resultsBody"),
    resultsMeta: document.getElementById("resultsMeta"),
    summaryStrip: document.getElementById("summaryStrip"),
    rankList: document.getElementById("rankList"),
  };

  function init() {
    bindDropzone(els.cvDropzone, els.cvInput, onCvFiles);
    bindDropzone(els.jdDropzone, els.jdInput, onJdFile);
    els.cvInput.addEventListener("change", () => onCvFiles(els.cvInput.files));
    els.jdInput.addEventListener("change", () => onJdFile(els.jdInput.files));
    els.skillsInput.addEventListener("input", renderSkillChips);
    els.form.addEventListener("submit", onSubmit);
    els.sampleBtn.addEventListener("click", onSample);
    els.resetBtn.addEventListener("click", resetForm);
    els.exportBtn.addEventListener("click", exportJson);
    els.helpBtn.addEventListener("click", toggleHelp);

    document.querySelectorAll("[data-jd-mode]").forEach((btn) => {
      btn.addEventListener("click", () => setJdMode(btn.dataset.jdMode));
    });

    refreshHealth();
    setInterval(refreshHealth, 15000);
  }

  function bindDropzone(zone, input, handler) {
    ["dragenter", "dragover"].forEach((evt) => {
      zone.addEventListener(evt, (e) => {
        e.preventDefault();
        zone.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach((evt) => {
      zone.addEventListener(evt, (e) => {
        e.preventDefault();
        zone.classList.remove("dragover");
      });
    });
    zone.addEventListener("drop", (e) => {
      handler(e.dataTransfer.files);
    });
  }

  function onCvFiles(fileList) {
    const incoming = Array.from(fileList || []);
    for (const file of incoming) {
      if (!isSupported(file.name)) {
        showError(`Unsupported CV format: ${file.name}. Use .txt, .pdf, or .docx.`);
        continue;
      }
      if (!state.cvFiles.some((f) => f.name === file.name && f.size === file.size)) {
        state.cvFiles.push(file);
      }
    }
    renderCvList();
    clearError();
  }

  function onJdFile(fileList) {
    const file = Array.from(fileList || [])[0];
    if (!file) return;
    if (!isSupported(file.name)) {
      showError(`Unsupported JD format: ${file.name}. Use .txt, .pdf, or .docx.`);
      return;
    }
    state.jdFile = file;
    els.jdFileName.textContent = file.name;
    els.jdFileName.classList.remove("hidden");
    clearError();
  }

  function isSupported(name) {
    return /\.(txt|pdf|docx)$/i.test(name || "");
  }

  function renderCvList() {
    els.cvList.innerHTML = "";
    state.cvFiles.forEach((file, index) => {
      const li = document.createElement("li");
      li.innerHTML = `<span>${escapeHtml(file.name)} <small>(${formatBytes(file.size)})</small></span>`;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove";
      remove.addEventListener("click", () => {
        state.cvFiles.splice(index, 1);
        renderCvList();
      });
      li.appendChild(remove);
      els.cvList.appendChild(li);
    });
  }

  function renderSkillChips() {
    const skills = parseSkills(els.skillsInput.value);
    els.skillChips.innerHTML = skills
      .map((s) => `<span class="chip">${escapeHtml(s)}</span>`)
      .join("");
  }

  function parseSkills(value) {
    return (value || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function setJdMode(mode) {
    state.jdMode = mode;
    document.querySelectorAll("[data-jd-mode]").forEach((btn) => {
      const active = btn.dataset.jdMode === mode;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    const paste = mode === "paste";
    els.jdText.classList.toggle("hidden", !paste);
    els.jdDropzone.classList.toggle("hidden", paste);
    if (paste) {
      els.jdFileName.classList.add("hidden");
    } else if (state.jdFile) {
      els.jdFileName.classList.remove("hidden");
    }
  }

  async function onSubmit(e) {
    e.preventDefault();
    clearError();

    const models = Array.from(document.querySelectorAll('input[name="model"]:checked')).map(
      (el) => el.value
    );
    if (models.length === 0) {
      showError("Select at least one model.");
      return;
    }
    if (state.cvFiles.length === 0) {
      showError("Upload at least one CV (.txt / .pdf / .docx).");
      return;
    }
    if (state.jdMode === "paste" && !els.jdText.value.trim()) {
      showError("Paste a job description, or switch to Upload.");
      return;
    }
    if (state.jdMode === "file" && !state.jdFile) {
      showError("Upload a job description file (.txt / .pdf / .docx).");
      return;
    }

    const formData = new FormData();
    state.cvFiles.forEach((file) => formData.append("cvs", file, file.name));
    if (state.jdMode === "paste") {
      formData.append("jd_text", els.jdText.value.trim());
    } else {
      formData.append("jd_file", state.jdFile, state.jdFile.name);
    }
    formData.append("models", models.join(","));
    formData.append("required_skills", els.skillsInput.value.trim());
    formData.append("use_mock", els.mockToggle.checked ? "true" : "false");
    formData.append("use_sample", "false");

    await runRank(formData, models);
  }

  async function onSample() {
    clearError();
    const models = Array.from(document.querySelectorAll('input[name="model"]:checked')).map(
      (el) => el.value
    );
    if (models.length === 0) {
      showError("Select at least one model.");
      return;
    }
    const formData = new FormData();
    formData.append("models", models.join(","));
    formData.append("required_skills", els.skillsInput.value.trim());
    formData.append("use_mock", els.mockToggle.checked ? "true" : "false");
    formData.append("use_sample", "true");
    await runRank(formData, models);
  }

  async function runRank(formData, models) {
    setLoading(true, `Scoring candidates with ${models.join(" + ")}…`);
    try {
      const resp = await fetch("/api/rank", { method: "POST", body: formData });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.detail || "Ranking failed.");
      }
      state.lastResult = data;
      renderResults(data);
    } catch (err) {
      showError(err.message || String(err));
      showEmpty();
    } finally {
      setLoading(false);
    }
  }

  function renderResults(data) {
    els.emptyState.classList.add("hidden");
    els.progressState.classList.add("hidden");
    els.resultsBody.classList.remove("hidden");
    els.exportBtn.disabled = false;

    const count = data.candidate_count || (data.ranked_cvs || []).length;
    const mode = data.used_mock ? "mock models" : "Ollama models";
    const sample = data.used_sample ? " · sample data" : "";
    els.resultsMeta.textContent = `${count} candidate${count === 1 ? "" : "s"} ranked with ${mode}${sample}.`;

    els.summaryStrip.innerHTML = [
      `<span class="summary-item">${count} CVs</span>`,
      `<span class="summary-item">${(data.models || []).join(" · ") || "models"}</span>`,
      data.used_mock ? `<span class="summary-item">Mock mode</span>` : "",
      data.parse_warnings
        ? `<span class="summary-item">${data.parse_warnings.length} parse warning(s)</span>`
        : "",
    ].join("");

    els.rankList.innerHTML = "";
    (data.ranked_cvs || []).forEach((row) => {
      els.rankList.appendChild(buildRankItem(row));
    });
  }

  function buildRankItem(row) {
    const li = document.createElement("li");
    li.className = "rank-item";

    const name = row.candidate_name || fileStem(row.source_path) || "Candidate";
    const source = (row.source_path || "").split(/[\\/]/).pop();

    const summary = document.createElement("button");
    summary.type = "button";
    summary.className = "rank-summary";
    summary.innerHTML = `
      <span class="rank-badge">${row.rank}</span>
      <span class="rank-main">
        <strong>${escapeHtml(name)}</strong>
        <span>${escapeHtml(source || "resume")} · ${(row.skills || []).slice(0, 4).join(", ") || "skills n/a"}</span>
      </span>
      <span class="score-pill">${Number(row.final_score).toFixed(1)}</span>
    `;

    const details = document.createElement("div");
    details.className = "rank-details hidden";

    (row.model_scores || []).forEach((ms) => {
      const block = document.createElement("div");
      block.className = "model-block";
      if (ms.error) {
        block.innerHTML = `
          <h4>${escapeHtml(ms.model)}</h4>
          <p class="error-note">Could not score: ${escapeHtml(ms.error)}</p>
        `;
      } else {
        const score = Number(ms.overall_score || 0);
        block.innerHTML = `
          <h4>${escapeHtml(ms.model)} · ${score.toFixed(1)}</h4>
          <div class="score-track"><i style="width:${Math.max(0, Math.min(100, score))}%"></i></div>
          <p class="explain">${escapeHtml(ms.explanation || "No explanation returned.")}</p>
          ${listBlock("Strengths", ms.strengths)}
          ${listBlock("Gaps", ms.gaps)}
        `;
      }
      details.appendChild(block);
    });

    summary.addEventListener("click", () => {
      details.classList.toggle("hidden");
    });

    li.appendChild(summary);
    li.appendChild(details);
    return li;
  }

  function listBlock(title, items) {
    if (!items || !items.length) return "";
    return `<p><strong>${title}</strong></p><ul class="bullets">${items
      .map((x) => `<li>${escapeHtml(x)}</li>`)
      .join("")}</ul>`;
  }

  function setLoading(loading, message) {
    els.runBtn.disabled = loading;
    els.sampleBtn.disabled = loading;
    els.runBtn.querySelector(".btn-label").textContent = loading ? "Ranking…" : "Rank candidates";
    els.runBtn.querySelector(".btn-spinner").hidden = !loading;
    if (loading) {
      els.emptyState.classList.add("hidden");
      els.resultsBody.classList.add("hidden");
      els.progressState.classList.remove("hidden");
      els.progressText.textContent = message || "Working…";
      els.exportBtn.disabled = true;
    }
  }

  function showEmpty() {
    els.progressState.classList.add("hidden");
    els.resultsBody.classList.add("hidden");
    els.emptyState.classList.remove("hidden");
    els.exportBtn.disabled = true;
    els.resultsMeta.textContent = "Run a sort to see scores, evidence, and model agreement.";
  }

  function resetForm() {
    state.cvFiles = [];
    state.jdFile = null;
    state.lastResult = null;
    els.form.reset();
    document.querySelectorAll('input[name="model"]').forEach((el) => {
      el.checked = true;
    });
    renderCvList();
    renderSkillChips();
    els.jdFileName.classList.add("hidden");
    setJdMode("paste");
    clearError();
    showEmpty();
  }

  function exportJson() {
    if (!state.lastResult) return;
    const blob = new Blob([JSON.stringify(state.lastResult, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ranked_results.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  function toggleHelp() {
    const open = els.helpPanel.hasAttribute("hidden");
    if (open) els.helpPanel.removeAttribute("hidden");
    else els.helpPanel.setAttribute("hidden", "");
    els.helpBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }

  async function refreshHealth() {
    try {
      const resp = await fetch("/api/health");
      const data = await resp.json();
      if (data.ollama) {
        els.statusPill.textContent = "Ollama online";
        els.statusPill.className = "status-pill ok";
      } else {
        els.statusPill.textContent = "Ollama offline — use Mock";
        els.statusPill.className = "status-pill warn";
      }
    } catch {
      els.statusPill.textContent = "UI server issue";
      els.statusPill.className = "status-pill warn";
    }
  }

  function showError(message) {
    els.formError.hidden = false;
    els.formError.textContent = message;
  }

  function clearError() {
    els.formError.hidden = true;
    els.formError.textContent = "";
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function fileStem(path) {
    const base = (path || "").split(/[\\/]/).pop() || "";
    return base.replace(/\.[^.]+$/, "");
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  init();
})();
