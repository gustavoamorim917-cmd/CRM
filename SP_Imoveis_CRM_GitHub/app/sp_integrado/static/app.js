const state = {
  stages: [],
  contacts: [],
  selectedContact: null,
  blasterLogIndex: 0,
  leadsSyncLogIndex: 0,
  leadsSyncLastStatus: "idle",
  propertySyncLogIndex: 0,
  propertySyncLastStatus: "idle",
  lastImoveisSubview: "",
  externalSyncLogIndex: 0,
  externalSyncLastStatus: "idle",
  propertyMarketing: "",
  externalPropertyMarketing: "",
  stageVisibleCounts: {},
};

const CARDS_PAGE_SIZE = 10;
const PROPERTY_TABLE_PAGE_SIZE = 20;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  window.setTimeout(() => node.classList.remove("show"), 3000);
}

const IMOVEIS_SUBVIEWS = ["selector", "selecao-externa", "apresentacoes"];

function setView(view) {
  // "imoveis" nao e uma view de conteudo em si - e o botao pai das
  // sub-abas (Seleção Interna / Seleção Externa / Apresentações prontas).
  // Clicar nele entra na ultima sub-aba visitada (ou na primeira, de cara).
  if (view === "imoveis") {
    view = state.lastImoveisSubview || IMOVEIS_SUBVIEWS[0];
  }
  const isImoveis = IMOVEIS_SUBVIEWS.includes(view);
  if (isImoveis) state.lastImoveisSubview = view;

  $$(".nav-button").forEach((button) => {
    const active = button.dataset.view === "imoveis" ? isImoveis : button.dataset.view === view;
    button.classList.toggle("active", active);
  });
  $$(".subnav-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  $("#imoveis-subnav").hidden = !isImoveis;
  $$(".view").forEach((section) => {
    section.classList.toggle("active", section.id === `view-${view}`);
  });
  const titles = {
    crm: ["CRM WhatsApp", "Pipeline comercial com contatos, notas e mensagens internas."],
    blaster: ["Disparador", "Controle de planilha, envio e logs em tempo real."],
    selector: ["Imóveis - Seleção Interna", "Filtro da planilha IMOBIZI e texto comercial pronto."],
    "selecao-externa": ["Imóveis - Seleção Externa", "Planilha do Vivareal (CODMAX) - atualizada sob demanda."],
    apresentacoes: ["Imóveis - Apresentações prontas", "Todos os index e PDFs já gerados, prontos para abrir."],
  };
  $("#view-title").textContent = titles[view][0];
  $("#view-subtitle").textContent = titles[view][1];
  $("#new-contact-btn").hidden = view !== "crm";
  $("#refresh-board-btn").hidden = view !== "crm";
  if (view === "apresentacoes") {
    runAction(loadPresentations);
  }
  if (view === "selecao-externa") {
    runAction(loadExternalPropertyTable);
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `Erro HTTP ${response.status}`);
  }
  return data;
}

function downloadBlob(blob, filename) {
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(link.href), 500);
}

function formatDateTime(value) {
  return value ? String(value).replace("T", " ") : "";
}

function createdTime(contact) {
  const raw = String(contact.created_at || "").trim();
  if (!raw) return 0;
  const normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
  const time = Date.parse(normalized);
  return Number.isNaN(time) ? 0 : time;
}

async function loadHealth() {
  try {
    const data = await requestJson("/api/health");
    const pieces = [];
    pieces.push(data.selenium_available ? "Selenium ok" : "Selenium ausente");
    $("#health-status").textContent = pieces.join(" / ");
  } catch {
    $("#health-status").textContent = "API indisponivel";
  }
}

async function loadBoard() {
  const data = await requestJson("/api/crm/board");
  state.stages = data.stages;
  state.contacts = data.contacts;
  fillStageSelects();
  renderDashboard();
  renderActiveContactsForBlaster();
  renderBoard();
}

function fillStageSelects() {
  const options = state.stages
    .map((stage) => `<option value="${escapeHtml(stage.id)}">${escapeHtml(stage.label)}</option>`)
    .join("");
  $("#new-contact-stage").innerHTML = options;
  $("#detail-stage").innerHTML = options;
  const blasterStage = $("#crm-blaster-stage");
  if (blasterStage) {
    const current = blasterStage.value || "ativo";
    const fallback = state.stages.find((stage) => stage.id === "ativo")?.id || state.stages[0]?.id || "";
    blasterStage.innerHTML = options;
    blasterStage.value = state.stages.some((stage) => stage.id === current) ? current : fallback;
  }
}

function getFilteredContacts() {
  const query = $("#crm-search").value.trim().toLowerCase();
  const kind = $("#crm-kind-filter").value;
  return state.contacts.filter((contact) => {
    const haystack = [
      contact.name,
      contact.phone,
      contact.kind,
      contact.last_message,
      contact.notes,
      contact.property_codes,
    ]
      .join(" ")
      .toLowerCase();
    const queryOk = !query || haystack.includes(query);
    const kindOk = !kind || contact.kind === kind;
    return queryOk && kindOk;
  });
}

function sortContactsByCreatedAt(contacts) {
  const order = $("#crm-date-sort")?.value || "created_desc";
  const direction = order === "created_asc" ? 1 : -1;
  return [...contacts].sort((a, b) => {
    const delta = createdTime(a) - createdTime(b);
    if (delta !== 0) return delta * direction;
    return ((a.id || 0) - (b.id || 0)) * direction;
  });
}

function renderDashboard() {
  const node = $("#crm-dashboard");
  if (!node) return;
  const total = state.contacts.length;
  const withPhone = state.contacts.filter((contact) => (contact.phone || "").replace(/\D/g, "")).length;
  const byStage = Object.fromEntries(state.stages.map((stage) => [stage.id, 0]));
  state.contacts.forEach((contact) => {
    if (byStage[contact.stage] !== undefined) byStage[contact.stage] += 1;
  });
  const topStage = state.stages
    .map((stage) => ({ ...stage, count: byStage[stage.id] || 0 }))
    .sort((a, b) => b.count - a.count)[0];
  const cards = [
    { label: "Contatos", value: total, hint: "Total no CRM" },
    { label: "Com telefone", value: withPhone, hint: "Prontos para WhatsApp" },
    { label: "Sem telefone", value: total - withPhone, hint: "Precisam completar cadastro" },
    { label: "Maior coluna", value: topStage ? topStage.count : 0, hint: topStage ? topStage.label : "-" },
  ];
  node.innerHTML = `
    ${cards
      .map(
        (card) => `
          <div class="dashboard-card">
            <span>${escapeHtml(card.label)}</span>
            <strong>${escapeHtml(card.value)}</strong>
            <em>${escapeHtml(card.hint)}</em>
          </div>
        `
      )
      .join("")}
    <div class="dashboard-card dashboard-wide">
      <span>Distribuicao por coluna</span>
      <div class="stage-bars">
        ${state.stages
          .map((stage) => {
            const count = byStage[stage.id] || 0;
            const pct = total ? Math.max(5, Math.round((count / total) * 100)) : 0;
            return `
              <div class="stage-bar-row">
                <small>${escapeHtml(stage.label)}</small>
                <div class="stage-bar"><div style="width:${pct}%"></div></div>
                <b>${count}</b>
              </div>
            `;
          })
          .join("")}
      </div>
    </div>
  `;
}

function selectedBlasterStage() {
  return $("#crm-blaster-stage")?.value || "ativo";
}

function selectedBlasterStageLabel() {
  const stage = state.stages.find((item) => item.id === selectedBlasterStage());
  return stage?.label || "coluna";
}

function contactsForBlaster() {
  const stage = selectedBlasterStage();
  return state.contacts.filter((contact) => contact.stage === stage && (contact.phone || "").replace(/\D/g, ""));
}

function renderActiveContactsForBlaster() {
  const list = $("#active-contact-list");
  if (!list) return;
  const contacts = contactsForBlaster();
  $("#active-contact-count").textContent = `${contacts.length} contato(s)`;
  if (!contacts.length) {
    list.innerHTML = `<div class="empty-list">Nenhum contato nesta coluna com telefone.</div>`;
    return;
  }
  list.innerHTML = contacts
    .map(
      (contact) => `
        <label class="active-contact-option">
          <input type="checkbox" value="${contact.id}">
          <span>
            <strong>${escapeHtml(contact.name || "Sem nome")}</strong>
            <small>${escapeHtml(contact.phone || "")}</small>
          </span>
        </label>
      `
    )
    .join("");
}

function renderBoard() {
  const contacts = sortContactsByCreatedAt(getFilteredContacts());
  const firstStage = state.stages[0]?.id || "ativo";
  const grouped = Object.fromEntries(state.stages.map((stage) => [stage.id, []]));
  contacts.forEach((contact) => {
    const stage = grouped[contact.stage] ? contact.stage : firstStage;
    grouped[stage].push(contact);
  });
  $("#crm-board").innerHTML = state.stages
    .map((stage) => {
      const cards = grouped[stage.id] || [];
      const visibleCount = state.stageVisibleCounts[stage.id] || CARDS_PAGE_SIZE;
      const visibleCards = cards.slice(0, visibleCount);
      const remaining = cards.length - visibleCards.length;
      return `
        <section class="kanban-column" data-stage="${escapeHtml(stage.id)}">
          <div class="column-head">
            <span class="drag-handle" draggable="true" data-stage="${escapeHtml(stage.id)}" title="Arraste para reordenar a coluna">&#8942;&#8942;</span>
            <div>
              <strong>${escapeHtml(stage.label)}</strong>
              <span class="column-count">${cards.length}</span>
            </div>
            <button class="ghost-button small delete-stage-btn" data-stage="${escapeHtml(stage.id)}">Excluir</button>
          </div>
          <div class="card-list">
            ${visibleCards.map(renderContactCard).join("")}
          </div>
          ${
            remaining > 0
              ? `<button class="show-more-btn" data-stage="${escapeHtml(stage.id)}">+ Ver mais ${remaining}</button>`
              : ""
          }
        </section>
      `;
    })
    .join("");

  $$(".contact-card").forEach((card) => {
    card.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("text/plain", card.dataset.id);
    });
    card.addEventListener("click", () => selectContact(Number(card.dataset.id)));
  });

  $$(".card-color-dot").forEach((dot) => {
    dot.addEventListener("click", (event) => {
      event.stopPropagation();
      const card = dot.closest(".contact-card");
      if (!card) return;
      const id = Number(card.dataset.id);
      const color = dot.classList.contains("is-active") ? "" : dot.dataset.color;
      runAction(() => setCardColor(id, color));
    });
  });

  $$(".delete-stage-btn").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      runAction(() => deleteStage(button.dataset.stage));
    });
  });

  $$(".show-more-btn").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const stageId = button.dataset.stage;
      state.stageVisibleCounts[stageId] = (state.stageVisibleCounts[stageId] || CARDS_PAGE_SIZE) + CARDS_PAGE_SIZE;
      renderBoard();
    });
  });

  $$(".drag-handle").forEach((handle) => {
    handle.addEventListener("dragstart", (event) => {
      event.stopPropagation();
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("application/x-stage-id", handle.dataset.stage);
    });
  });

  $$(".kanban-column").forEach((column) => {
    column.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (event.dataTransfer.types.includes("application/x-stage-id")) {
        column.classList.add("drag-target");
      }
    });
    column.addEventListener("dragleave", () => column.classList.remove("drag-target"));
    column.addEventListener("drop", async (event) => {
      event.preventDefault();
      column.classList.remove("drag-target");
      const draggedStage = event.dataTransfer.getData("application/x-stage-id");
      if (draggedStage) {
        await reorderStages(draggedStage, column.dataset.stage);
        return;
      }
      const id = Number(event.dataTransfer.getData("text/plain"));
      const stage = column.dataset.stage;
      await updateContact(id, { stage });
    });
  });

  populateContactQuickSelects();
}

function populateContactQuickSelects() {
  const contacts = [...state.contacts].sort((a, b) =>
    (a.name || "").localeCompare(b.name || "", "pt-BR", { sensitivity: "base" })
  );
  const options =
    `<option value="">Selecionar contato...</option>` +
    contacts
      .map((contact) => {
        const label = contact.phone ? `${contact.name || "Sem nome"} — ${contact.phone}` : contact.name || "Sem nome";
        return `<option value="${contact.id}">${escapeHtml(label)}</option>`;
      })
      .join("");
  $$(".contact-quick-select").forEach((select) => {
    const current = select.value;
    select.innerHTML = options;
    if (current && contacts.some((contact) => String(contact.id) === current)) {
      select.value = current;
    }
  });
}

async function reorderStages(draggedStageId, targetStageId) {
  if (draggedStageId === targetStageId) return;
  const order = state.stages.map((stage) => stage.id);
  const fromIndex = order.indexOf(draggedStageId);
  const toIndex = order.indexOf(targetStageId);
  if (fromIndex === -1 || toIndex === -1) return;
  order.splice(fromIndex, 1);
  order.splice(toIndex, 0, draggedStageId);

  const previousStages = state.stages;
  state.stages = order.map((id) => state.stages.find((stage) => stage.id === id)).filter(Boolean);
  renderBoard();
  try {
    await requestJson("/api/crm/stages/reorder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order }),
    });
  } catch (error) {
    state.stages = previousStages;
    renderBoard();
    toast(error.message || "Nao foi possivel reordenar as colunas.");
  }
}

const CARD_COLORS = [
  { id: "verde", label: "Verde" },
  { id: "amarelo", label: "Amarelo" },
  { id: "azul", label: "Azul" },
  { id: "vermelho", label: "Vermelho" },
];

function cardColorPickerHtml(contact) {
  return CARD_COLORS.map(
    (color) => `
      <button
        type="button"
        class="card-color-dot card-color-${color.id} ${contact.color === color.id ? "is-active" : ""}"
        data-color="${color.id}"
        title="${color.label}"
        aria-label="Marcar como ${color.label}"
      ></button>
    `
  ).join("");
}

function renderContactCard(contact) {
  const text = contact.last_message || contact.notes || "Sem registro recente.";
  const colorClass = contact.color ? `card-color-${contact.color}` : "";
  return `
    <article class="contact-card ${colorClass}" draggable="true" data-id="${contact.id}">
      <h3>${escapeHtml(contact.name || "Sem nome")}</h3>
      <p>${escapeHtml(contact.phone || "Sem telefone")}</p>
      <p>${escapeHtml(text).slice(0, 150)}</p>
      <div class="card-color-picker">${cardColorPickerHtml(contact)}</div>
      <div class="card-meta">
        <span class="tag">${escapeHtml(contact.kind || "Cliente")}</span>
        <span class="muted">${escapeHtml(formatDateTime(contact.updated_at))}</span>
      </div>
    </article>
  `;
}

async function createStage() {
  const label = window.prompt("Nome da nova coluna");
  if (!label || !label.trim()) return;
  await requestJson("/api/crm/stages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label: label.trim() }),
  });
  await loadBoard();
  toast("Coluna criada.");
}

async function exportColumns() {
  const response = await fetch("/api/crm/export_columns", { method: "POST" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `Erro HTTP ${response.status}`);
  }
  if ((response.headers.get("Content-Type") || "").includes("application/json")) {
    const data = await response.json();
    toast(`Colunas salvas em ${data.path}`);
    return;
  }
  const blob = await response.blob();
  downloadBlob(blob, "crm_colunas_sp_imoveis.xlsx");
}

async function deleteStage(stageId) {
  const stage = state.stages.find((item) => item.id === stageId);
  if (!stage) return;
  if (!window.confirm(`Excluir a coluna "${stage.label}"? Os contatos serao movidos para outra coluna.`)) {
    return;
  }
  await requestJson(`/api/crm/stages/${encodeURIComponent(stageId)}`, { method: "DELETE" });
  if (state.selectedContact?.stage === stageId) closeDrawer();
  await loadBoard();
  toast("Coluna excluida.");
}

async function updateContact(id, payload) {
  const data = await requestJson(`/api/crm/conversations/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const index = state.contacts.findIndex((contact) => contact.id === id);
  if (index >= 0) state.contacts[index] = data.contact;
  if (state.selectedContact?.id === id) state.selectedContact = data.contact;
  renderBoard();
  if (state.selectedContact?.id === id) fillDrawer(data.contact);
}

async function setCardColor(id, color) {
  await updateContact(id, { color });
}

function openContactModal() {
  $("#contact-modal").hidden = false;
  $("#contact-form").elements.name.focus();
}

function closeContactModal() {
  $("#contact-modal").hidden = true;
  $("#contact-form").reset();
}

async function createContact(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  const data = await requestJson("/api/crm/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  closeContactModal();
  state.contacts.unshift(data.contact);
  renderBoard();
  selectContact(data.contact.id);
  toast("Contato criado.");
}

async function selectContact(id) {
  state.selectedContact = state.contacts.find((contact) => contact.id === id);
  if (!state.selectedContact) return;
  showDrawerPanel();
  fillDrawer(state.selectedContact);
  $("#drawer-empty").hidden = true;
  $("#drawer-content").hidden = false;
  const data = await requestJson(`/api/crm/conversations/${id}/messages`);
  renderMessages(data.messages);
}

function fillDrawer(contact) {
  $("#detail-title").textContent = contact.name || "Contato";
  $("#detail-phone-label").textContent = contact.phone || "Sem telefone";
  $("#detail-name").value = contact.name || "";
  $("#detail-phone").value = contact.phone || "";
  $("#detail-kind").value = contact.kind || "Cliente";
  $("#detail-stage").value = contact.stage || "ativo";
  $("#detail-color").value = contact.color || "";
  $("#detail-created-at").value = formatDateTime(contact.created_at);
  $("#detail-notes").value = contact.notes || "";
}

function closeDrawer() {
  hideDrawerPanel();
}

function hideDrawerPanel() {
  state.selectedContact = null;
  $(".app-shell").classList.add("drawer-collapsed");
  $("#drawer-empty").hidden = false;
  $("#drawer-content").hidden = true;
}

function showDrawerPanel() {
  $(".app-shell").classList.remove("drawer-collapsed");
}

async function saveSelectedContact() {
  if (!state.selectedContact) return;
  await updateContact(state.selectedContact.id, {
    name: $("#detail-name").value,
    phone: $("#detail-phone").value,
    kind: $("#detail-kind").value,
    stage: $("#detail-stage").value,
    color: $("#detail-color").value,
    created_at: $("#detail-created-at").value,
    notes: $("#detail-notes").value,
  });
  toast("Contato atualizado.");
}

async function clearSelectedNotes() {
  if (!state.selectedContact) return;
  if (!$("#detail-notes").value.trim()) {
    toast("Nao ha observacoes para excluir.");
    return;
  }
  if (!window.confirm("Excluir as observacoes deste contato?")) return;
  $("#detail-notes").value = "";
  await updateContact(state.selectedContact.id, { notes: "" });
  toast("Observacoes excluidas.");
}

function renderMessages(messages) {
  const list = $("#message-list");
  if (!messages.length) {
    list.innerHTML = `<div class="message-item"><small>Historico</small>Sem notas ainda.</div>`;
    return;
  }
  list.innerHTML = messages
    .map((message) => {
      const label = { note: "Nota", in: "Recebida", out: "Enviada" }[message.direction] || "Nota";
      return `
        <div class="message-item ${escapeHtml(message.direction)}">
          <div class="message-head">
            <small>${label} - ${escapeHtml((message.created_at || "").replace("T", " "))}</small>
            <button class="ghost-button small delete-message-btn" data-message-id="${message.id}">Excluir</button>
          </div>
          <div>${escapeHtml(message.body).replaceAll("\n", "<br>")}</div>
        </div>
      `;
    })
    .join("");
  $$(".delete-message-btn").forEach((button) => {
    button.addEventListener("click", () => runAction(() => deleteMessage(Number(button.dataset.messageId))));
  });
  list.scrollTop = list.scrollHeight;
}

async function deleteMessage(messageId) {
  if (!state.selectedContact) return;
  if (!window.confirm("Excluir esta nota do historico?")) return;
  await requestJson(`/api/crm/conversations/${state.selectedContact.id}/messages/${messageId}`, {
    method: "DELETE",
  });
  await selectContact(state.selectedContact.id);
  await loadBoard();
  toast("Nota excluida.");
}

async function addMessage(direction) {
  if (!state.selectedContact) {
    toast("Selecione um contato.");
    return;
  }
  const body = $("#message-body").value.trim();
  if (!body) {
    toast("Digite uma mensagem ou nota.");
    return;
  }
  await requestJson(`/api/crm/conversations/${state.selectedContact.id}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ direction, body }),
  });
  $("#message-body").value = "";
  await selectContact(state.selectedContact.id);
  await loadBoard();
}

function openWhatsApp() {
  if (!state.selectedContact) return;
  const phone = ($("#detail-phone").value || "").replace(/\D/g, "");
  if (!phone) {
    toast("Contato sem telefone.");
    return;
  }
  const text = $("#message-body").value.trim();
  const url = `https://web.whatsapp.com/send?phone=${phone}&text=${encodeURIComponent(text)}`;
  window.open(url, "_blank", "noopener,noreferrer");
}

async function importCrmContacts(event) {
  const file = event.target.files[0];
  if (!file) return;
  const confirmed = window.confirm(
    "Aplicar edicao em massa?\n\nA = alterar\nE = excluir\nI = inserir\nEm branco = ignorar"
  );
  if (!confirmed) {
    event.target.value = "";
    return;
  }
  const form = new FormData();
  form.append("file", file);
  form.append("stage", "ativo");
  const data = await requestJson("/api/crm/import_contacts", { method: "POST", body: form });
  event.target.value = "";
  await loadBoard();
  const summary = [
    `${data.inserted || data.imported || 0} inserido(s)`,
    `${data.updated || 0} alterado(s)`,
    `${data.deleted || 0} excluido(s)`,
    `${data.ignored || 0} ignorado(s)`,
  ];
  const failed = data.failed ? ` ${data.failed} falha(s).` : "";
  toast(`Edicao em massa aplicada: ${summary.join(", ")}.${failed}`);
}

function renderTable(table, columns, rows) {
  table.innerHTML = `
    <thead><tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join("")}</tr></thead>
    <tbody>
      ${rows
        .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`)
        .join("")}
    </tbody>
  `;
}

async function uploadBlasterFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  const data = await requestJson("/api/blaster/upload", { method: "POST", body: form });
  $("#blaster-file-label").textContent = `${file.name} - ${data.rows} linha(s)`;
  renderTable($("#blaster-preview"), data.columns, data.preview);
  $("#start-blaster-btn").disabled = false;
  $("#optimize-blaster-btn").disabled = false;
  state.blasterLogIndex = 0;
  $("#blaster-log").innerHTML = "";
  toast("Planilha carregada.");
}

function selectedActiveContactIds() {
  return $$("#active-contact-list input[type='checkbox']:checked").map((item) => Number(item.value));
}

function selectAllActiveContacts() {
  $$("#active-contact-list input[type='checkbox']").forEach((item) => {
    item.checked = true;
  });
}

function clearActiveContactSelection() {
  $$("#active-contact-list input[type='checkbox']").forEach((item) => {
    item.checked = false;
  });
}

async function loadActiveContactsIntoBlaster() {
  const ids = selectedActiveContactIds();
  if (!ids.length) {
    toast("Selecione pelo menos um contato da coluna.");
    return;
  }
  const message = $("#crm-blaster-message").value.trim();
  if (!message) {
    toast("Digite a mensagem para os contatos selecionados.");
    return;
  }
  const data = await requestJson("/api/blaster/from_crm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contact_ids: ids, stage: selectedBlasterStage(), message }),
  });
  renderTable($("#blaster-preview"), data.columns, data.preview);
  $("#blaster-file-label").textContent = `CRM ${selectedBlasterStageLabel()} - ${data.rows} contato(s) carregado(s)`;
  $("#start-blaster-btn").disabled = false;
  $("#optimize-blaster-btn").disabled = false;
  state.blasterLogIndex = 0;
  $("#blaster-log").innerHTML = "";
  const skipped = data.skipped ? ` ${data.skipped} contato(s) ignorado(s).` : "";
  toast(`${data.rows} contato(s) carregado(s) no disparador.${skipped}`);
}

async function optimizeBlasterSheet() {
  const response = await fetch("/api/blaster/optimize", { method: "POST" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || "Falha ao otimizar");
  }
  const blob = await response.blob();
  downloadBlob(blob, "contatos_otimizados.xlsx");
}

async function startBlaster() {
  await requestJson("/api/blaster/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      qr_wait: Number($("#qr-wait").value || 60),
      delay_min: Number($("#delay-min").value || 10),
      delay_max: Number($("#delay-max").value || 20),
    }),
  });
  state.blasterLogIndex = 0;
  $("#blaster-log").innerHTML = "";
  $("#start-blaster-btn").disabled = true;
  $("#pause-blaster-btn").disabled = false;
  $("#stop-blaster-btn").disabled = false;
  toast("Disparador iniciado.");
}

async function pauseBlaster() {
  const data = await requestJson("/api/blaster/pause", { method: "POST" });
  $("#pause-blaster-btn").textContent = data.action === "paused" ? "Retomar" : "Pausar";
}

async function stopBlaster() {
  await requestJson("/api/blaster/stop", { method: "POST" });
  $("#start-blaster-btn").disabled = false;
  $("#pause-blaster-btn").disabled = true;
  $("#stop-blaster-btn").disabled = true;
  $("#pause-blaster-btn").textContent = "Pausar";
}

function appendBlasterLogs(logs) {
  const box = $("#blaster-log");
  logs.forEach((entry) => {
    const line = document.createElement("div");
    line.className = "log-line";
    line.innerHTML = `
      <span class="log-time">${escapeHtml(entry.t)}</span>
      <span class="log-${escapeHtml(entry.k)}">${escapeHtml(entry.msg)}</span>
    `;
    box.appendChild(line);
  });
  if (logs.length) box.scrollTop = box.scrollHeight;
}

async function pollBlaster() {
  try {
    const data = await requestJson(`/api/blaster/status?since=${state.blasterLogIndex}`);
    state.blasterLogIndex = data.log_index;
    appendBlasterLogs(data.logs || []);
    const labels = {
      idle: "Inativo",
      starting: "Iniciando",
      waiting_qr: "Aguardando QR",
      running: "Disparando",
      paused: "Pausado",
      done: "Concluido",
      error: "Erro",
    };
    $("#blaster-status").textContent = labels[data.status] || data.status;
    $("#stat-total").textContent = data.total || 0;
    $("#stat-sent").textContent = data.sent || 0;
    $("#stat-failed").textContent = data.failed || 0;
    $("#stat-countdown").textContent = data.countdown ? `${data.countdown}s` : "-";
    const done = (data.sent || 0) + (data.failed || 0);
    const percent = data.total ? Math.round((done / data.total) * 100) : 0;
    $("#blaster-progress").style.width = `${percent}%`;
    $("#current-target").textContent = data.current ? `Enviando para ${data.current}` : "Nenhum envio em andamento.";
    const active = ["starting", "waiting_qr", "running", "paused"].includes(data.status);
    if (!active) {
      $("#pause-blaster-btn").disabled = true;
      $("#stop-blaster-btn").disabled = true;
      $("#pause-blaster-btn").textContent = "Pausar";
      if ($("#blaster-file").files.length) $("#start-blaster-btn").disabled = false;
    }
  } catch {
    // Keep the UI quiet if the dev server is restarting.
  }
}

function openLeadsSyncPanel() {
  $("#leads-sync-panel").hidden = false;
}

function appendLeadsSyncLogs(logs) {
  const box = $("#leads-sync-log");
  logs.forEach((entry) => {
    const line = document.createElement("div");
    line.className = "log-line";
    line.innerHTML = `
      <span class="log-time">${escapeHtml(entry.t)}</span>
      <span class="log-${escapeHtml(entry.k)}">${escapeHtml(entry.msg)}</span>
    `;
    box.appendChild(line);
  });
  if (logs.length) box.scrollTop = box.scrollHeight;
}

async function startLeadsSync() {
  openLeadsSyncPanel();
  await requestJson("/api/crm/sync_leads/start", { method: "POST" });
  state.leadsSyncLogIndex = 0;
  $("#leads-sync-log").innerHTML = "";
  $("#leads-sync-summary").textContent = "Sincronização iniciada - o Chrome vai abrir para logar no Imobzi.";
  $("#sync-leads-btn").disabled = true;
  $("#stop-leads-sync-btn").disabled = false;
  toast("Sincronização de Leads iniciada.");
}

async function stopLeadsSync() {
  await requestJson("/api/crm/sync_leads/stop", { method: "POST" });
  $("#stop-leads-sync-btn").disabled = true;
}

async function pollLeadsSync() {
  try {
    const data = await requestJson(`/api/crm/sync_leads/status?since=${state.leadsSyncLogIndex}`);
    state.leadsSyncLogIndex = data.log_index;
    appendLeadsSyncLogs(data.logs || []);
    const labels = { idle: "Inativo", running: "Sincronizando", done: "Concluído", error: "Erro" };
    $("#leads-sync-status").textContent = labels[data.status] || data.status;

    const active = data.status === "running";
    $("#sync-leads-btn").disabled = active;
    $("#stop-leads-sync-btn").disabled = !active;

    const justFinished = state.leadsSyncLastStatus === "running" && data.status !== "running";
    state.leadsSyncLastStatus = data.status;

    if (data.status === "done" && data.result) {
      const r = data.result;
      $("#leads-sync-summary").textContent =
        `Concluído: ${r.novos_adicionados || 0} lead(s) novo(s) adicionados. ` +
        `${r.ja_no_crm || 0} já existiam no CRM, ${r.sem_telefone || 0} sem telefone válido.`;
      if (justFinished && r.novos_adicionados) {
        await loadBoard();
        toast(`${r.novos_adicionados} lead(s) novo(s) adicionados ao CRM.`);
      }
    } else if (data.status === "error") {
      $("#leads-sync-summary").textContent = `Erro: ${data.error || "falha desconhecida."}`;
      if (justFinished) toast("Falha na sincronização de Leads.");
    }
  } catch {
    // Keep the UI quiet if the dev server is restarting.
  }
}

function setPropertyTypeOptions(types) {
  const select = $("#tipo-imovel");
  if (!select) return;
  const current = select.value || "Todos";
  const options = [];
  (types && types.length ? types : ["Todos"]).forEach((type) => {
    const label = String(type || "").trim();
    if (label && !options.includes(label)) options.push(label);
  });
  if (!options.includes("Todos")) options.unshift("Todos");
  select.innerHTML = options.map((type) => `<option>${escapeHtml(type)}</option>`).join("");
  select.value = options.includes(current) ? current : "Todos";
}

async function loadPropertyOptions() {
  try {
    const data = await requestJson("/api/properties/options");
    setPropertyTypeOptions(data.types || ["Todos"]);
  } catch {
    setPropertyTypeOptions(["Todos"]);
  }
}

const propertyTable = { columns: [], rows: [], filters: {}, visibleCount: PROPERTY_TABLE_PAGE_SIZE };

function shortenPropertySource(path) {
  if (!path) return "";
  const parts = String(path).split(/[\\/]/);
  return parts[parts.length - 1] || path;
}

async function loadPropertyTable() {
  try {
    const data = await requestJson("/api/properties/table");
    propertyTable.columns = data.columns || [];
    propertyTable.rows = data.rows || [];
    propertyTable.filters = {};
    propertyTable.visibleCount = PROPERTY_TABLE_PAGE_SIZE;
    $("#property-count").textContent = `${propertyTable.rows.length} imóvel(is)`;
    $("#property-source").textContent = data.source ? `Planilha: ${shortenPropertySource(data.source)}` : "Nenhuma planilha encontrada.";
    $("#search-properties-btn").disabled = propertyTable.rows.length === 0;
    renderPropertyTable();
  } catch (error) {
    propertyTable.columns = [];
    propertyTable.rows = [];
    propertyTable.filters = {};
    propertyTable.visibleCount = PROPERTY_TABLE_PAGE_SIZE;
    $("#property-count").textContent = "Nenhuma planilha";
    $("#property-source").textContent = error.message || "Nenhuma planilha encontrada.";
    $("#search-properties-btn").disabled = true;
    renderPropertyTable();
  }
}

async function reloadPropertyTable() {
  await requestJson("/api/properties/reload", { method: "POST" });
  await loadPropertyOptions();
  await loadPropertyTable();
}

function appendPropertySyncLogs(logs) {
  const box = $("#property-sync-log");
  logs.forEach((entry) => {
    const line = document.createElement("div");
    line.className = "log-line";
    line.innerHTML = `
      <span class="log-time">${escapeHtml(entry.t)}</span>
      <span class="log-${escapeHtml(entry.k)}">${escapeHtml(entry.msg)}</span>
    `;
    box.appendChild(line);
  });
  if (logs.length) box.scrollTop = box.scrollHeight;
}

async function startPropertySync() {
  await requestJson("/api/properties/sync/start", { method: "POST" });
  state.propertySyncLogIndex = 0;
  $("#property-sync-log").hidden = false;
  $("#property-sync-log").innerHTML = "";
  $("#property-source").textContent = "Atualizando planilha do Imobzi... (Chrome vai abrir, pode levar alguns minutos)";
  $("#reload-property-btn").disabled = true;
  $("#stop-property-sync-btn").hidden = false;
  toast("Atualização de imóveis iniciada.");
}

async function stopPropertySync() {
  await requestJson("/api/properties/sync/stop", { method: "POST" });
  $("#stop-property-sync-btn").disabled = true;
}

async function pollPropertySync() {
  try {
    const data = await requestJson(`/api/properties/sync/status?since=${state.propertySyncLogIndex}`);
    state.propertySyncLogIndex = data.log_index;
    appendPropertySyncLogs(data.logs || []);

    const active = data.status === "running";
    $("#reload-property-btn").disabled = active;
    $("#stop-property-sync-btn").hidden = !active;
    $("#stop-property-sync-btn").disabled = false;

    const justFinished = state.propertySyncLastStatus === "running" && data.status !== "running";
    state.propertySyncLastStatus = data.status;

    if (data.status === "done" && justFinished) {
      await reloadPropertyTable();
      toast("Planilha de imóveis atualizada.");
    } else if (data.status === "error" && justFinished) {
      $("#property-source").textContent = `Erro ao atualizar: ${data.error || "falha desconhecida."}`;
      toast("Falha ao atualizar a planilha de imóveis.");
    }
  } catch {
    // Keep the UI quiet if the dev server is restarting.
  }
}

function uniquePropertyColumnValues(column) {
  const values = new Set();
  propertyTable.rows.forEach((row) => {
    const value = row[column];
    if (value) values.add(value);
  });
  return Array.from(values).sort((a, b) => a.localeCompare(b, "pt-BR"));
}

function renderPropertyTableHead() {
  const headRow = $("#property-table-head");
  const filterRow = $("#property-table-filters");
  if (!headRow || !filterRow) return;
  headRow.innerHTML = propertyTable.columns.map((col) => `<th>${escapeHtml(col)}</th>`).join("");
  filterRow.innerHTML = propertyTable.columns
    .map((col) => {
      const options = uniquePropertyColumnValues(col);
      if (options.length && options.length <= 60) {
        return `
          <th>
            <select data-filter-col="${escapeHtml(col)}">
              <option value="">Todos</option>
              ${options.map((opt) => `<option value="${escapeHtml(opt)}">${escapeHtml(opt)}</option>`).join("")}
            </select>
          </th>
        `;
      }
      return `<th><input type="text" placeholder="Filtrar..." data-filter-col="${escapeHtml(col)}"></th>`;
    })
    .join("");
  filterRow.querySelectorAll("[data-filter-col]").forEach((el) => {
    const eventName = el.tagName === "SELECT" ? "change" : "input";
    el.addEventListener(eventName, () => {
      propertyTable.filters[el.dataset.filterCol] = el.value.trim().toLowerCase();
      propertyTable.visibleCount = PROPERTY_TABLE_PAGE_SIZE;
      renderPropertyTableBody();
    });
  });
}

function getFilteredPropertyRows() {
  const activeFilters = Object.entries(propertyTable.filters).filter(([, value]) => value);
  if (!activeFilters.length) return propertyTable.rows;
  return propertyTable.rows.filter((row) =>
    activeFilters.every(([col, value]) => String(row[col] || "").toLowerCase().includes(value))
  );
}

function renderPropertyTableBody() {
  const rows = getFilteredPropertyRows();
  const body = $("#property-table-body");
  const countLabel = $("#property-table-count");
  const moreContainer = $("#property-table-more");
  const visibleRows = rows.slice(0, propertyTable.visibleCount);
  const remaining = rows.length - visibleRows.length;
  if (countLabel) {
    countLabel.textContent =
      rows.length === propertyTable.rows.length
        ? `${rows.length} linha(s)`
        : `${rows.length} de ${propertyTable.rows.length} linha(s)`;
  }
  if (body) {
    body.innerHTML = visibleRows.length
      ? visibleRows
          .map((row) => `<tr>${propertyTable.columns.map((col) => `<td>${escapeHtml(row[col] || "")}</td>`).join("")}</tr>`)
          .join("")
      : `<tr><td colspan="${propertyTable.columns.length || 1}">Nenhuma linha encontrada.</td></tr>`;
  }
  if (moreContainer) {
    moreContainer.innerHTML =
      remaining > 0
        ? `<button class="ghost-button small" id="property-table-more-btn" type="button">+ Ver mais ${Math.min(remaining, PROPERTY_TABLE_PAGE_SIZE)}</button>`
        : "";
    const moreBtn = $("#property-table-more-btn");
    if (moreBtn) {
      moreBtn.addEventListener("click", () => {
        propertyTable.visibleCount += PROPERTY_TABLE_PAGE_SIZE;
        renderPropertyTableBody();
      });
    }
  }
}

function renderPropertyTable() {
  renderPropertyTableHead();
  renderPropertyTableBody();
}

// ---------------------------------------------------------------------
// Seleção Externa (planilha do Vivareal) - mesmo padrão de tabela+filtro
// da Seleção Interna acima, só que apontando para outra fonte de dados.
// ---------------------------------------------------------------------

const externalPropertyTable = { columns: [], rows: [], filters: {}, visibleCount: PROPERTY_TABLE_PAGE_SIZE };

async function loadExternalPropertyTable() {
  try {
    const data = await requestJson("/api/properties/external/table");
    externalPropertyTable.columns = data.columns || [];
    externalPropertyTable.rows = data.rows || [];
    externalPropertyTable.filters = {};
    externalPropertyTable.visibleCount = PROPERTY_TABLE_PAGE_SIZE;
    $("#external-property-count").textContent = `${externalPropertyTable.rows.length} imóvel(is)`;
    $("#external-property-source").textContent = data.source
      ? `Planilha: ${shortenPropertySource(data.source)}`
      : "Nenhuma planilha encontrada.";
    $("#external-search-btn").disabled = externalPropertyTable.rows.length === 0;
    renderExternalPropertyTable();
  } catch (error) {
    externalPropertyTable.columns = [];
    externalPropertyTable.rows = [];
    externalPropertyTable.filters = {};
    externalPropertyTable.visibleCount = PROPERTY_TABLE_PAGE_SIZE;
    $("#external-property-count").textContent = "Nenhuma planilha";
    $("#external-property-source").textContent = error.message || "Nenhuma planilha encontrada.";
    $("#external-search-btn").disabled = true;
    renderExternalPropertyTable();
  }
}

async function loadExternalPropertyOptions() {
  try {
    const data = await requestJson("/api/properties/external/options");
    setExternalPropertyTypeOptions(data.types || ["Todos"]);
  } catch {
    setExternalPropertyTypeOptions(["Todos"]);
  }
}

function setExternalPropertyTypeOptions(types) {
  const select = $("#external-tipo-imovel");
  if (!select) return;
  const current = select.value || "Todos";
  const options = types && types.length ? types : ["Todos"];
  select.innerHTML = options.map((type) => `<option>${escapeHtml(type)}</option>`).join("");
  select.value = options.includes(current) ? current : "Todos";
}

function uniqueExternalPropertyColumnValues(column) {
  const values = new Set();
  externalPropertyTable.rows.forEach((row) => {
    const value = row[column];
    if (value) values.add(value);
  });
  return Array.from(values).sort((a, b) => a.localeCompare(b, "pt-BR"));
}

function renderExternalPropertyTableHead() {
  const headRow = $("#external-property-table-head");
  const filterRow = $("#external-property-table-filters");
  if (!headRow || !filterRow) return;
  headRow.innerHTML = externalPropertyTable.columns.map((col) => `<th>${escapeHtml(col)}</th>`).join("");
  filterRow.innerHTML = externalPropertyTable.columns
    .map((col) => {
      const options = uniqueExternalPropertyColumnValues(col);
      if (options.length && options.length <= 60) {
        return `
          <th>
            <select data-filter-col="${escapeHtml(col)}">
              <option value="">Todos</option>
              ${options.map((opt) => `<option value="${escapeHtml(opt)}">${escapeHtml(opt)}</option>`).join("")}
            </select>
          </th>
        `;
      }
      return `<th><input type="text" placeholder="Filtrar..." data-filter-col="${escapeHtml(col)}"></th>`;
    })
    .join("");
  filterRow.querySelectorAll("[data-filter-col]").forEach((el) => {
    const eventName = el.tagName === "SELECT" ? "change" : "input";
    el.addEventListener(eventName, () => {
      externalPropertyTable.filters[el.dataset.filterCol] = el.value.trim().toLowerCase();
      externalPropertyTable.visibleCount = PROPERTY_TABLE_PAGE_SIZE;
      renderExternalPropertyTableBody();
    });
  });
}

function getFilteredExternalPropertyRows() {
  const activeFilters = Object.entries(externalPropertyTable.filters).filter(([, value]) => value);
  if (!activeFilters.length) return externalPropertyTable.rows;
  return externalPropertyTable.rows.filter((row) =>
    activeFilters.every(([col, value]) => String(row[col] || "").toLowerCase().includes(value))
  );
}

function renderExternalPropertyTableBody() {
  const rows = getFilteredExternalPropertyRows();
  const body = $("#external-property-table-body");
  const countLabel = $("#external-property-table-count");
  const moreContainer = $("#external-property-table-more");
  const visibleRows = rows.slice(0, externalPropertyTable.visibleCount);
  const remaining = rows.length - visibleRows.length;
  if (countLabel) {
    countLabel.textContent =
      rows.length === externalPropertyTable.rows.length
        ? `${rows.length} linha(s)`
        : `${rows.length} de ${externalPropertyTable.rows.length} linha(s)`;
  }
  if (body) {
    body.innerHTML = visibleRows.length
      ? visibleRows
          .map(
            (row) =>
              `<tr>${externalPropertyTable.columns.map((col) => `<td>${escapeHtml(row[col] || "")}</td>`).join("")}</tr>`
          )
          .join("")
      : `<tr><td colspan="${externalPropertyTable.columns.length || 1}">Nenhuma linha encontrada.</td></tr>`;
  }
  if (moreContainer) {
    moreContainer.innerHTML =
      remaining > 0
        ? `<button class="ghost-button small" id="external-property-table-more-btn" type="button">+ Ver mais ${Math.min(remaining, PROPERTY_TABLE_PAGE_SIZE)}</button>`
        : "";
    const moreBtn = $("#external-property-table-more-btn");
    if (moreBtn) {
      moreBtn.addEventListener("click", () => {
        externalPropertyTable.visibleCount += PROPERTY_TABLE_PAGE_SIZE;
        renderExternalPropertyTableBody();
      });
    }
  }
}

function renderExternalPropertyTable() {
  renderExternalPropertyTableHead();
  renderExternalPropertyTableBody();
}

function appendExternalSyncLogs(logs) {
  const box = $("#external-sync-log");
  logs.forEach((entry) => {
    const line = document.createElement("div");
    line.className = "log-line";
    line.innerHTML = `
      <span class="log-time">${escapeHtml(entry.t)}</span>
      <span class="log-${escapeHtml(entry.k)}">${escapeHtml(entry.msg)}</span>
    `;
    box.appendChild(line);
  });
  if (logs.length) box.scrollTop = box.scrollHeight;
}

async function startExternalSync() {
  await requestJson("/api/properties/external/sync/start", { method: "POST" });
  state.externalSyncLogIndex = 0;
  $("#external-sync-log").hidden = false;
  $("#external-sync-log").innerHTML = "";
  $("#external-property-source").textContent =
    "Atualizando planilha externa... (Chrome vai abrir - um por link da lista, pode levar bastante tempo)";
  $("#external-reload-btn").disabled = true;
  $("#stop-external-sync-btn").hidden = false;
  toast("Atualização da Seleção Externa iniciada.");
}

async function stopExternalSync() {
  await requestJson("/api/properties/external/sync/stop", { method: "POST" });
  $("#stop-external-sync-btn").disabled = true;
}

async function pollExternalSync() {
  try {
    const data = await requestJson(`/api/properties/external/sync/status?since=${state.externalSyncLogIndex}`);
    state.externalSyncLogIndex = data.log_index;
    appendExternalSyncLogs(data.logs || []);

    const active = data.status === "running";
    $("#external-reload-btn").disabled = active;
    $("#stop-external-sync-btn").hidden = !active;
    $("#stop-external-sync-btn").disabled = false;

    const justFinished = state.externalSyncLastStatus === "running" && data.status !== "running";
    state.externalSyncLastStatus = data.status;

    if (data.status === "done" && justFinished) {
      await loadExternalPropertyTable();
      toast("Planilha externa atualizada.");
    } else if (data.status === "error" && justFinished) {
      $("#external-property-source").textContent = `Erro ao atualizar: ${data.error || "falha desconhecida."}`;
      toast("Falha ao atualizar a planilha externa.");
    }
  } catch {
    // Keep the UI quiet if the dev server is restarting.
  }
}

function getExternalPropertyPayload() {
  return {
    client_name: $("#external-client-name").value,
    report_title: $("#external-report-title").value,
    area_min: $("#external-area-min").value,
    area_max: $("#external-area-max").value,
    valor_min: $("#external-valor-min").value,
    valor_max: $("#external-valor-max").value,
    region_or_cep: $("#external-region-or-cep").value,
    price_mode: $("#external-price-mode").value,
    tipo_imovel: $("#external-tipo-imovel").value,
    only_active: $("#external-only-active").checked,
    max_results: $("#external-max-results").value,
    selected_codes: $("#external-selected-codes").value,
  };
}

async function searchExternalProperties() {
  const data = await requestJson("/api/properties/external/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(getExternalPropertyPayload()),
  });
  state.externalPropertyMarketing = data.marketing_text || "";
  $("#external-marketing-text").value = state.externalPropertyMarketing;
  $("#external-result-count").textContent = `${data.count} imóvel(is)`;
  renderExternalPropertyResultsSummary(data.count || 0);
  $("#external-export-json-btn").disabled = data.count === 0;
  $("#external-export-pdf-btn").disabled = data.count === 0;
  $("#external-export-web-btn").disabled = data.count === 0;
}

function renderExternalPropertyResultsSummary(count) {
  const node = $("#external-property-results");
  if (!count) {
    node.innerHTML = `<div class="property-card"><p>Nenhum imóvel encontrado.</p></div>`;
    return;
  }
  node.innerHTML = `
    <div class="property-card">
      <p>${count} imóvel(is) selecionado(s) pelos filtros.</p>
      <p class="muted">Clique em "Baixar apresenta&ccedil;&atilde;o web" para montar a p&aacute;gina com as fotos dos an&uacute;ncios do Vivareal. An&uacute;ncios com link indispon&iacute;vel s&atilde;o ignorados automaticamente.</p>
    </div>
  `;
}

async function exportExternalPropertyPdf() {
  const btn = $("#external-export-pdf-btn");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Montando PDF...";
  toast("Gerando a proposta em PDF. Isso pode levar alguns segundos por imóvel.");
  try {
    const data = await requestJson("/api/properties/external/export_pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(getExternalPropertyPayload()),
    });
    toast(`PDF salvo: ${data.filename}`);
    window.open(data.url, "_blank");
    loadPresentations().catch(() => {});
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

async function exportExternalWebPresentation() {
  const btn = $("#external-export-web-btn");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Buscando fotos dos anúncios...";
  toast("Gerando apresentação. Isso pode levar alguns segundos por imóvel.");
  try {
    const data = await requestJson("/api/properties/external/export_web", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(getExternalPropertyPayload()),
    });
    toast(`Apresentação salva: ${data.filename}`);
    window.open(data.url, "_blank");
    loadPresentations().catch(() => {});
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

async function copyExternalMarketingText() {
  const text = $("#external-marketing-text").value;
  if (!text.trim()) {
    toast("Nenhum texto para copiar.");
    return;
  }
  await navigator.clipboard.writeText(text);
  toast("Texto copiado.");
}

async function useExternalMarketingOnSelectedContact() {
  const text = $("#external-marketing-text").value.trim();
  if (!text) {
    toast("Gere uma seleção primeiro.");
    return;
  }
  const pickedId = Number($("#external-marketing-contact-select").value);
  if (pickedId) {
    await selectContact(pickedId);
  }
  if (!state.selectedContact) {
    toast("Selecione um contato no seletor acima ou no CRM.");
    setView("crm");
    return;
  }
  $("#message-body").value = text;
  setView("crm");
  toast(`Texto carregado no contato ${state.selectedContact.name || ""}.`.trim());
}

function getPropertyPayload() {
  return {
    client_name: $("#client-name").value,
    report_title: $("#report-title").value,
    area_min: $("#area-min").value,
    area_max: $("#area-max").value,
    valor_min: $("#valor-min").value,
    valor_max: $("#valor-max").value,
    region_or_cep: $("#region-or-cep").value,
    price_mode: $("#price-mode").value,
    tipo_imovel: $("#tipo-imovel").value,
    only_active: $("#only-active").checked,
    max_results: $("#max-results").value,
    selected_codes: $("#selected-codes").value,
  };
}

async function searchProperties() {
  const data = await requestJson("/api/properties/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(getPropertyPayload()),
  });
  state.propertyMarketing = data.marketing_text || "";
  $("#marketing-text").value = state.propertyMarketing;
  $("#selector-result-count").textContent = `${data.count} imóvel(is)`;
  renderPropertyResultsSummary(data.count || 0);
  $("#export-json-btn").disabled = data.count === 0;
  $("#export-pdf-btn").disabled = data.count === 0;
  $("#export-web-btn").disabled = data.count === 0;
}

function renderPropertyResultsSummary(count) {
  const node = $("#property-results");
  if (!count) {
    node.innerHTML = `<div class="property-card"><p>Nenhum imóvel encontrado.</p></div>`;
    return;
  }
  node.innerHTML = `
    <div class="property-card">
      <p>${count} imóvel(is) selecionado(s) pelos filtros.</p>
      <p class="muted">Clique em "Baixar apresenta&ccedil;&atilde;o web" para montar a p&aacute;gina com as fotos dos an&uacute;ncios. An&uacute;ncios com link indispon&iacute;vel s&atilde;o ignorados automaticamente.</p>
    </div>
  `;
}

async function exportPropertyPdf() {
  const btn = $("#export-pdf-btn");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Montando PDF...";
  toast("Gerando a proposta em PDF. Isso pode levar alguns segundos por imóvel.");
  try {
    const data = await requestJson("/api/properties/export_pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(getPropertyPayload()),
    });
    toast(`PDF salvo: ${data.filename}`);
    window.open(data.url, "_blank");
    loadPresentations().catch(() => {});
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

async function exportWebPresentation() {
  const btn = $("#export-web-btn");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Buscando fotos dos anúncios...";
  toast("Gerando apresentação. Isso pode levar alguns segundos por imóvel.");
  try {
    const data = await requestJson("/api/properties/export_web", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(getPropertyPayload()),
    });
    toast(`Apresentação salva: ${data.filename}`);
    window.open(data.url, "_blank");
    loadPresentations().catch(() => {});
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

function presentationCardHtml(file) {
  const sizeKb = Math.max(1, Math.round(file.size / 1024));
  return `
    <div class="presentation-card">
      <a class="presentation-card-link" href="${escapeHtml(file.url)}" target="_blank" rel="noreferrer">
        <strong>${escapeHtml(file.name)}</strong>
        <span class="muted">${escapeHtml(file.modified_label)} &middot; ${sizeKb} KB</span>
      </a>
      <div class="button-row presentation-card-actions">
        <button class="secondary-button small assign-presentation-btn" type="button" data-url="${escapeHtml(file.url)}" data-name="${escapeHtml(file.name)}">Atribuir ao lead</button>
      </div>
    </div>
  `;
}

async function loadPresentations() {
  const data = await requestJson("/api/presentations/list");
  const indexList = $("#presentations-index-list");
  const pdfList = $("#presentations-pdf-list");
  indexList.innerHTML = data.index.length
    ? data.index.map(presentationCardHtml).join("")
    : `<p class="muted">Nenhum index gerado ainda.</p>`;
  pdfList.innerHTML = data.pdf.length
    ? data.pdf.map(presentationCardHtml).join("")
    : `<p class="muted">Nenhum PDF gerado ainda.</p>`;
  $("#presentations-index-count").textContent = `${data.index.length} arquivo(s)`;
  $("#presentations-pdf-count").textContent = `${data.pdf.length} arquivo(s)`;
  $$(".assign-presentation-btn").forEach((button) => {
    button.addEventListener("click", () =>
      runAction(() => assignPresentationToContact(button.dataset.url, button.dataset.name))
    );
  });
}

async function assignPresentationToContact(url, name) {
  const select = $("#presentations-contact-select");
  const pickedId = Number(select.value);
  if (!pickedId) {
    toast("Selecione um contato no seletor acima para atribuir.");
    return;
  }
  await selectContact(pickedId);
  if (!state.selectedContact) {
    toast("Contato não encontrado. Atualize a lista do CRM.");
    return;
  }
  const contactId = state.selectedContact.id;
  const contactName = state.selectedContact.name || "contato";
  const absoluteUrl = new URL(url, window.location.origin).href;
  const noteBody = `Apresentação atribuída: ${name}\n${absoluteUrl}`;
  await requestJson(`/api/crm/conversations/${contactId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ direction: "note", body: noteBody }),
  });
  $("#message-body").value = noteBody;
  await selectContact(contactId);
  await loadBoard();
  setView("crm");
  toast(`Apresentação atribuída ao card de ${contactName}.`);
}

async function copyMarketingText() {
  const text = $("#marketing-text").value;
  if (!text.trim()) {
    toast("Nenhum texto para copiar.");
    return;
  }
  await navigator.clipboard.writeText(text);
  toast("Texto copiado.");
}

async function useMarketingOnSelectedContact() {
  const text = $("#marketing-text").value.trim();
  if (!text) {
    toast("Gere uma seleção primeiro.");
    return;
  }
  const pickedId = Number($("#marketing-contact-select").value);
  if (pickedId) {
    await selectContact(pickedId);
  }
  if (!state.selectedContact) {
    toast("Selecione um contato no seletor acima ou no CRM.");
    setView("crm");
    return;
  }
  $("#message-body").value = text;
  setView("crm");
  toast(`Texto carregado no contato ${state.selectedContact.name || ""}.`.trim());
}

function wireEvents() {
  $$(".nav-button, .subnav-button").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  $("#refresh-board-btn").addEventListener("click", loadBoard);
  $("#new-contact-btn").addEventListener("click", openContactModal);
  $("#new-stage-btn").addEventListener("click", () => runAction(createStage));
  $("#export-columns-btn").addEventListener("click", () => runAction(exportColumns));
  $("#sync-leads-btn").addEventListener("click", () => runAction(startLeadsSync));
  $("#stop-leads-sync-btn").addEventListener("click", () => runAction(stopLeadsSync));
  $("#hide-leads-sync-panel-btn").addEventListener("click", () => {
    $("#leads-sync-panel").hidden = true;
  });
  $("#clear-leads-sync-log-btn").addEventListener("click", () => {
    $("#leads-sync-log").innerHTML = "";
  });
  $("#close-contact-modal").addEventListener("click", closeContactModal);
  $("#contact-form").addEventListener("submit", createContact);
  $("#crm-search").addEventListener("input", renderBoard);
  $("#crm-kind-filter").addEventListener("change", renderBoard);
  $("#crm-date-sort").addEventListener("change", renderBoard);
  $("#crm-import-file").addEventListener("change", (event) => runAction(() => importCrmContacts(event)));
  $("#hide-empty-drawer-btn").addEventListener("click", hideDrawerPanel);
  $("#close-drawer-btn").addEventListener("click", closeDrawer);
  $("#save-contact-btn").addEventListener("click", () => runAction(saveSelectedContact));
  $("#clear-notes-btn").addEventListener("click", () => runAction(clearSelectedNotes));
  $("#open-whatsapp-btn").addEventListener("click", openWhatsApp);
  $$("[data-add-message]").forEach((button) => {
    button.addEventListener("click", () => runAction(() => addMessage(button.dataset.addMessage)));
  });

  $("#blaster-file").addEventListener("change", (event) => runAction(() => uploadBlasterFile(event)));
  $("#crm-blaster-stage").addEventListener("change", renderActiveContactsForBlaster);
  $("#select-all-active-btn").addEventListener("click", selectAllActiveContacts);
  $("#clear-active-selection-btn").addEventListener("click", clearActiveContactSelection);
  $("#load-active-blaster-btn").addEventListener("click", () => runAction(loadActiveContactsIntoBlaster));
  $("#optimize-blaster-btn").addEventListener("click", () => runAction(optimizeBlasterSheet));
  $("#start-blaster-btn").addEventListener("click", () => runAction(startBlaster));
  $("#pause-blaster-btn").addEventListener("click", () => runAction(pauseBlaster));
  $("#stop-blaster-btn").addEventListener("click", () => runAction(stopBlaster));
  $("#clear-log-btn").addEventListener("click", () => {
    $("#blaster-log").innerHTML = "";
  });

  $("#reload-property-btn").addEventListener("click", () => runAction(startPropertySync));
  $("#stop-property-sync-btn").addEventListener("click", () => runAction(stopPropertySync));
  $("#external-reload-btn").addEventListener("click", () => runAction(startExternalSync));
  $("#stop-external-sync-btn").addEventListener("click", () => runAction(stopExternalSync));
  $("#external-search-btn").addEventListener("click", () => runAction(searchExternalProperties));
  $("#external-export-json-btn").addEventListener("click", () => {
    window.location.href = "/api/properties/external/export_json";
  });
  $("#external-export-pdf-btn").addEventListener("click", () => runAction(exportExternalPropertyPdf));
  $("#external-export-web-btn").addEventListener("click", () => runAction(exportExternalWebPresentation));
  $("#external-copy-marketing-btn").addEventListener("click", () => runAction(copyExternalMarketingText));
  $("#external-use-message-btn").addEventListener("click", () => runAction(useExternalMarketingOnSelectedContact));
  $("#search-properties-btn").addEventListener("click", () => runAction(searchProperties));
  $("#export-json-btn").addEventListener("click", () => {
    window.location.href = "/api/properties/export_json";
  });
  $("#export-pdf-btn").addEventListener("click", () => runAction(exportPropertyPdf));
  $("#export-web-btn").addEventListener("click", () => runAction(exportWebPresentation));
  $("#copy-marketing-btn").addEventListener("click", () => runAction(copyMarketingText));
  $("#use-message-btn").addEventListener("click", () => runAction(useMarketingOnSelectedContact));
  $("#refresh-presentations-btn").addEventListener("click", () => runAction(loadPresentations));
}

async function runAction(action) {
  try {
    await action();
  } catch (error) {
    toast(error.message || "Erro inesperado.");
  }
}

async function boot() {
  wireEvents();
  await loadHealth();
  await loadBoard();
  await loadPropertyOptions();
  await loadPropertyTable();
  await loadExternalPropertyOptions();
  await loadExternalPropertyTable();
  await loadPresentations();
  window.setInterval(pollBlaster, 1200);
  window.setInterval(pollLeadsSync, 1500);
  window.setInterval(pollPropertySync, 1500);
  window.setInterval(pollExternalSync, 1500);
}

boot().catch((error) => toast(error.message || "Falha ao iniciar."));
