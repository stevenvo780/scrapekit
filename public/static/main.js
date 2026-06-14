const form = document.getElementById("process-form");
const statusEl = document.getElementById("form-status");
const tableBody = document.getElementById("documents-body");
const emptyState = document.getElementById("documents-empty");
const documentsTable = document.getElementById("documents-table");
const searchInput = document.getElementById("search-input");
const searchResultsEl = document.getElementById("search-results");
const searchFeedbackEl = document.getElementById("search-feedback");
const sourceFilterEl = document.getElementById("source-filter");

let searchTimeoutId = null;
let searchAbortController = null;

function formatDate(isoString) {
  const date = new Date(isoString);
  return date.toLocaleString("es-CO");
}

async function submitDocument(event) {
  event.preventDefault();
  const formData = new FormData(form);
  const documentId = formData.get("document_id");
  const sourceKey = formData.get("source_key");
  const apiKey = document.getElementById("api-key-input")?.value || "";

  if (!documentId) {
    statusEl.textContent = "Debes ingresar un ID";
    statusEl.className = "status error";
    return;
  }
  if (!apiKey) {
    statusEl.textContent = "Debes ingresar la API Key";
    statusEl.className = "status error";
    return;
  }

  statusEl.textContent = "Procesando documento...";
  statusEl.className = "status info";

  try {
    const response = await fetch("/api/documents", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
      body: JSON.stringify({ document_id: documentId, source_key: sourceKey }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || "Error desconocido");
    }

    const doc = await response.json();
    statusEl.textContent = `Documento ${doc.document_id} procesado correctamente.`;
    statusEl.className = "status success";
    form.reset();
    insertOrUpdateRow(doc);
  } catch (error) {
    console.error(error);
    statusEl.textContent = `Error: ${error.message}`;
    statusEl.className = "status error";
  }
}

function createCell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

function insertOrUpdateRow(doc) {
  if (emptyState) emptyState.style.display = "none";
  if (documentsTable) documentsTable.style.display = "table";

  let row = tableBody?.querySelector(`[data-document-id="${CSS.escape(doc.document_id)}"]`);
  if (!row) {
    row = document.createElement("tr");
    row.dataset.documentId = doc.document_id;
    tableBody?.prepend(row);
  }

  // Build cells via DOM to avoid innerHTML with untrusted server data
  row.replaceChildren(
    createCell(doc.document_id),
    createCell(doc.source_key),
    createCell(doc.country),
    createCell(doc.filename),
    createCell(String(doc.total_pages)),
    createCell(formatDate(doc.processed_at)),
    (() => {
      const td = document.createElement("td");
      const a = document.createElement("a");
      a.className = "button-link";
      a.href = `/document/${encodeURIComponent(doc.document_id)}`;
      a.textContent = "Ver";
      td.appendChild(a);
      return td;
    })(),
  );
}

form?.addEventListener("submit", submitDocument);

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function highlightSnippet(snippet, query) {
  if (!snippet) return "";
  const escapedSnippet = escapeHtml(snippet);
  if (!query) return escapedSnippet;
  const pattern = new RegExp(`(${escapeRegExp(query)})`, "gi");
  return escapedSnippet.replace(pattern, "<mark>$1</mark>");
}

function clearSearchResults(message = "") {
  if (searchResultsEl) searchResultsEl.innerHTML = "";
  if (searchFeedbackEl) {
    searchFeedbackEl.textContent = message;
    searchFeedbackEl.className = message ? "status info" : "status";
  }
}

function renderSearchResults(results, query) {
  if (!searchResultsEl || !searchFeedbackEl) return;
  searchResultsEl.innerHTML = "";
  if (!results.length) {
    searchFeedbackEl.textContent = "Sin coincidencias.";
    searchFeedbackEl.className = "status info";
    return;
  }

  searchFeedbackEl.textContent = `${results.length} resultado${results.length === 1 ? "" : "s"} encontrados.`;
  searchFeedbackEl.className = "status success";

  results.forEach((result) => {
    const item = document.createElement("li");
    item.className = "search-result";

    // Title link — textContent is safe
    const link = document.createElement("a");
    link.href = `/document/${encodeURIComponent(result.document_id)}`;
    link.className = "search-result__title";
    link.textContent = result.filename;

    // Meta spans — build via DOM to avoid XSS with untrusted field values
    const meta = document.createElement("div");
    meta.className = "search-result__meta";
    const metaTexts = [
      `${result.country} - ${result.institution}`,
      formatDate(result.processed_at),
      `${result.matches} coincidencia${result.matches === 1 ? "" : "s"}`,
      `${result.total_pages} paginas`,
    ];
    metaTexts.forEach((text) => {
      const span = document.createElement("span");
      span.textContent = text;
      meta.appendChild(span);
    });

    // Snippet: highlightSnippet escapes all server text via escapeHtml first,
    // then only injects <mark> tags it constructs itself — safe to use innerHTML.
    const snippet = document.createElement("p");
    snippet.className = "search-result__snippet";
    snippet.innerHTML = highlightSnippet(result.snippet, query);

    item.appendChild(link);
    item.appendChild(meta);
    item.appendChild(snippet);
    searchResultsEl.appendChild(item);
  });
}

async function performSearch(query) {
  if (!searchFeedbackEl) return;
  if (searchAbortController) searchAbortController.abort();
  searchAbortController = new AbortController();

  searchFeedbackEl.textContent = "Buscando...";
  searchFeedbackEl.className = "status info";

  const source = sourceFilterEl?.value || "";
  const url = `/api/search?q=${encodeURIComponent(query)}${source ? `&source=${encodeURIComponent(source)}` : ""}`;

  try {
    const response = await fetch(url, { signal: searchAbortController.signal });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || "Error al buscar");
    }
    const results = await response.json();
    renderSearchResults(results, query);
  } catch (error) {
    if (error.name === "AbortError") return;
    console.error(error);
    searchFeedbackEl.textContent = `Error: ${error.message}`;
    searchFeedbackEl.className = "status error";
  }
}

function handleSearchInput(event) {
  const value = event.target.value.trim();
  if (searchTimeoutId) { clearTimeout(searchTimeoutId); searchTimeoutId = null; }
  if (!value) { clearSearchResults(""); return; }
  if (value.length < 2) { clearSearchResults("Escribe al menos dos caracteres."); return; }
  searchTimeoutId = setTimeout(() => performSearch(value), 300);
}

searchInput?.addEventListener("input", handleSearchInput);
sourceFilterEl?.addEventListener("change", () => {
  const q = searchInput?.value?.trim();
  if (q && q.length >= 2) performSearch(q);
});
