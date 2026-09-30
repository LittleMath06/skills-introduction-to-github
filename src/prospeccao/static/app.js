/* Interações da interface. Sem scripts inline (CSP script-src 'self'). */
(function () {
  "use strict";
  const csrf = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  function toast(msg, isErr) {
    const box = document.getElementById("toast");
    if (!box) return;
    const el = document.createElement("div");
    el.textContent = msg;
    if (isErr) el.className = "err";
    box.appendChild(el);
    setTimeout(() => el.remove(), isErr ? 7000 : 3500);
  }

  async function api(method, url, body, isForm) {
    const opts = { method, headers: { "X-CSRF-Token": csrf(), "Accept": "application/json" }, credentials: "same-origin" };
    if (body !== undefined) {
      if (isForm) opts.body = body;
      else { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    }
    let resp;
    try { resp = await fetch(url, opts); } catch (e) { throw new Error("Sem conexão com o servidor"); }
    if (resp.status === 401) { window.location = "/login"; throw new Error("Sessão expirada"); }
    const data = resp.status === 204 ? null : await resp.json().catch(() => null);
    if (!resp.ok) {
      let msg = (data && data.detail) || ("Erro " + resp.status);
      if (data && data.erros) msg += ": " + data.erros.map((e) => (e.campo ? e.campo + " — " : "") + e.erro).join("; ");
      throw new Error(msg);
    }
    return data;
  }

  const reload = (delay) => setTimeout(() => window.location.reload(), delay || 400);

  // Barras: largura definida via JS (CSP não permite style inline)
  document.querySelectorAll("[data-width]").forEach((el) => { el.style.width = Math.max(0, Math.min(100, parseFloat(el.dataset.width) || 0)) + "%"; });
  // Logo com fallback para iniciais
  document.querySelectorAll("img[data-fallback]").forEach((img) => {
    img.addEventListener("error", () => { const p = img.parentElement; p.textContent = img.dataset.fallback; });
  });
  document.querySelectorAll("[data-autosubmit]").forEach((el) => el.addEventListener("change", () => el.form.submit()));

  // Acompanhamento de processos em background
  function watchJob(id, panel) {
    const tick = async () => {
      let job;
      try { job = await api("GET", "/api/jobs/" + id); } catch (e) { return; }
      const txt = job.processados + (job.total ? " / " + job.total : "") + " processados";
      if (panel) {
        panel.innerHTML = "";
        const div = document.createElement("div");
        div.className = "notice" + (job.status === "failed" ? " err" : "");
        div.textContent = (job.status === "running" || job.status === "queued" ? "Em andamento… " : job.status === "done" ? "Concluído: " : "Falhou: ") + txt + (job.mensagem ? " — " + job.mensagem : "");
        if (job.total) { const pr = document.createElement("progress"); pr.max = job.total; pr.value = job.processados; div.appendChild(pr); }
        panel.appendChild(div);
      }
      document.querySelectorAll('[data-job="' + id + '"] [data-job-text]').forEach((el) => { el.textContent = txt; });
      document.querySelectorAll('[data-job="' + id + '"] [data-job-status]').forEach((el) => { el.textContent = job.status; });
      document.querySelectorAll('[data-job="' + id + '"] [data-job-progress]').forEach((el) => { el.max = job.total || 1; el.value = job.processados; });
      if (job.status === "queued" || job.status === "running") setTimeout(tick, 1500);
      else if (panel && panel.dataset.reloadOnDone) reload(800);
      else if (!panel) reload(600);
    };
    tick();
  }
  document.querySelectorAll("[data-job]").forEach((el) => {
    const st = el.querySelector("[data-job-status]");
    if (!st || st.textContent === "running" || st.textContent === "queued") watchJob(el.dataset.job, null);
  });
  const jobPanel = document.querySelector("[data-job-panel][data-job-id]");
  if (jobPanel) {
    api("GET", "/api/jobs/" + jobPanel.dataset.jobId).then((j) => {
      if (j.status === "running" || j.status === "queued") { jobPanel.dataset.reloadOnDone = "1"; watchJob(j.id, jobPanel); }
    }).catch(() => {});
  }

  function rowValues(row) {
    const out = {};
    row.querySelectorAll("input, select, textarea").forEach((el) => {
      if (!el.name) return;
      out[el.name] = el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value;
    });
    return out;
  }

  // Ações por clique
  document.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-action]");
    if (!btn || btn.tagName === "SELECT") return;
    const a = btn.dataset.action;
    if (btn.dataset.confirm && !window.confirm(btn.dataset.confirm)) return;
    btn.disabled = true;
    try {
      if (a === "save-lead") {
        await api("POST", "/api/companies/" + btn.dataset.id + "/save"); toast("Lead salvo"); reload();
      } else if (a === "lead-toggle") {
        const body = {}; body[btn.dataset.field] = btn.dataset.value === "true";
        await api("PATCH", "/api/leads/" + btn.dataset.lead, body); toast("Atualizado"); reload();
      } else if (a === "discard") {
        let lead = btn.dataset.lead;
        if (!lead) lead = (await api("POST", "/api/companies/" + btn.dataset.id + "/save")).id;
        await api("PATCH", "/api/leads/" + lead, { discarded: true });
        toast("Descartado — não aparecerá mais nas buscas (veja em Leads › Descartados)");
        const li = btn.closest(".result"); if (li) li.remove(); else reload();
      } else if (a === "copy") {
        await navigator.clipboard.writeText(btn.dataset.value); toast("Copiado");
      } else if (a === "enrich") {
        const job = await api("POST", "/api/companies/" + btn.dataset.id + "/enrich");
        toast("Buscando contatos no site oficial…"); watchJob(job.id, null);
      } else if (a === "icms") {
        const job = await api("POST", "/api/companies/" + btn.dataset.id + "/icms");
        toast("Consultando SEFAZ…"); watchJob(job.id, null);
      } else if (a === "lookup") {
        await api("POST", "/api/companies/lookup", { cnpj: btn.dataset.cnpj, force: true }); toast("Cadastro atualizado"); reload();
      } else if (a === "delete-fiscal") {
        if (!window.confirm("Excluir este registro fiscal?")) return;
        await api("DELETE", "/api/fiscal/" + btn.dataset.id); toast("Excluído"); reload();
      } else if (a === "delete-contact") {
        if (!window.confirm("Excluir este contato da base?")) return;
        await api("DELETE", "/api/contacts/" + btn.dataset.id); toast("Contato excluído"); reload();
      } else if (a === "delete-note") {
        if (!window.confirm("Excluir esta observação?")) return;
        await api("DELETE", "/api/notes/" + btn.dataset.id); toast("Excluída"); reload();
      } else if (a === "set-segment") {
        const sel = btn.parentElement.querySelector("[data-field-segment]");
        if (!sel.value) { toast("Escolha um segmento", true); return; }
        await api("PATCH", "/api/companies/" + btn.dataset.id, { segment_id: Number(sel.value) }); toast("Segmento salvo"); reload();
      } else if (a === "clear-segment") {
        await api("PATCH", "/api/companies/" + btn.dataset.id, { clear_manual_segment: true }); toast("Classificação automática restaurada"); reload();
      } else if (a === "admin") {
        const body = btn.dataset.body ? JSON.parse(btn.dataset.body) : undefined;
        const job = await api("POST", btn.dataset.endpoint, body);
        toast("Processo iniciado (#" + job.id + ")"); reload(800);
      } else if (a === "save-segment") {
        const row = btn.closest("[data-segment-row]"); const v = rowValues(row);
        if (btn.dataset.id === "new") await api("POST", "/api/segments", v);
        else await api("PATCH", "/api/segments/" + btn.dataset.id, v);
        toast("Segmento salvo — recalculando em segundo plano"); reload(800);
      } else if (a === "save-status") {
        const row = btn.closest("[data-status-row]"); const v = rowValues(row);
        if (btn.dataset.id === "new") await api("POST", "/api/lead-statuses", v);
        else await api("PATCH", "/api/lead-statuses/" + btn.dataset.id, v);
        toast("Status salvo"); reload();
      }
    } catch (e) {
      toast(e.message, true);
    } finally {
      btn.disabled = false;
    }
  });

  document.addEventListener("change", async (ev) => {
    const sel = ev.target.closest('select[data-action="lead-status"]');
    if (!sel) return;
    try { await api("PATCH", "/api/leads/" + sel.dataset.lead, { status_id: Number(sel.value) }); toast("Status atualizado"); }
    catch (e) { toast(e.message, true); }
  });

  // Formulários
  document.addEventListener("submit", async (ev) => {
    const form = ev.target.closest("form[data-form]");
    if (!form) return;
    ev.preventDefault();
    const kind = form.dataset.form;
    const btn = form.querySelector('[type="submit"]'); if (btn) btn.disabled = true;
    const fd = new FormData(form);
    try {
      if (kind === "note") {
        await api("POST", "/api/leads/" + form.dataset.lead + "/notes", { text: fd.get("text") }); toast("Observação adicionada"); reload();
      } else if (kind === "customer-cnpj") {
        const r = await api("PATCH", "/api/customers/" + form.dataset.id, { cnpj: fd.get("cnpj") });
        toast(r.status === "ok" ? "Cliente vinculado — recalculando perfil" : "CNPJ salvo; a empresa entrará na base na próxima importação/consulta");
        reload(800);
      } else if (kind === "website") {
        await api("PATCH", "/api/companies/" + form.dataset.id, { website: fd.get("website") || "" }); toast("Site salvo"); reload();
      } else if (kind === "fiscal") {
        const body = {};
        fd.forEach((v, k) => { if (v !== "") body[k] = k === "confidence" ? Number(v) : v; });
        await api("POST", "/api/companies/" + form.dataset.id + "/fiscal", body); toast("Registrado"); reload();
      } else if (kind === "lookup") {
        const r = await api("POST", "/api/companies/lookup", { cnpj: fd.get("cnpj") });
        window.location = "/empresas/" + r.empresa.id;
      } else if (kind === "import-customers") {
        const job = await api("POST", "/api/customers/import", fd, true);
        const panel = document.querySelector("[data-job-panel]");
        panel.dataset.reloadOnDone = "1"; watchJob(job.id, panel); toast("Importação iniciada");
      } else if (kind === "weights") {
        const body = { similarity: {}, potential: {}, segment_affinity: {} };
        fd.forEach((v, k) => { const [grp, key] = k.split(/\.(.+)/); body[grp][key] = Number(v); });
        await api("PUT", "/api/settings/weights", body); toast("Pesos salvos — recalculando em segundo plano"); reload(800);
      }
    } catch (e) {
      toast(e.message, true);
    } finally {
      if (btn) btn.disabled = false;
    }
  });
})();
