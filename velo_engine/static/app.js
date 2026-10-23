const CATEGORY_COLORS = { identification: "#DC2626", contact: "#2563EB", financial: "#7C3AED", personal: "#059669", health: "#DB2777" };
const CATEGORY_LABELS = { identification: "Identificación", contact: "Contacto", financial: "Financiero", personal: "Personal", health: "Salud" };
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
const APP_VERSION = document.querySelector('meta[name="app-version"]')?.getAttribute("content") || "";

function apiFetch(url, options = {}) {
    const opts = { credentials: "same-origin", ...options };
    const method = (opts.method || "GET").toUpperCase();
    opts.headers = { ...(opts.headers || {}) };

    if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
        opts.headers["X-CSRF-Token"] = CSRF_TOKEN;
    }

    return fetch(url, opts);
}

let currentStep = 0;
let documentText = "";
let findings = [];
let layersActive = [];
let layersAvailable = [];
let selectedFile = null;
let manualSelection = null;
let manualCategory = "personal";
let findingCounter = 0;
let visualSession = null;
let visualPages = [];
let visualAvailable = false;
let visualMode = null;
let visualOcrUsed = false;
let visualReason = "";
let nativeRedactionAvailable = false;
let currentFormat = "txt";
let appliedOriginal = null;
let appliedSignature = null;
let applyingOriginal = false;

const SAMPLE_TEXT = "EXPEDIENTE SINTÉTICO DE PRUEBA - Nº TEST/2026/001\n\nSolicitante: Persona de Ejemplo Uno\nDNI: 00000000T\nNIE del conviviente: X0000000T\nFecha de nacimiento: 15/03/1978\nDomicilio: Calle de Ejemplo, nº 42, 3ºB\nCódigo postal: 28045, Madrid\n\nTeléfono de contacto: 600 123 123\nCorreo electrónico: persona.ejemplo@dominio.test\n\nNº de la Seguridad Social: 28/12345678/05\nCuenta bancaria: ES9121000418450200051332\n\nINFORME DE PRUEBA:\nLa persona solicitante acude al servicio derivada por un centro municipal. Este texto es sintético y se incluye únicamente para verificar la detección local de patrones sensibles.";

function catLabel(cat) { return CATEGORY_LABELS[cat] || cat; }

function setStepLabels() {
    const tab3 = document.getElementById("tab3");
    const tab4 = document.getElementById("tab4");
    const note3 = tab3.querySelector(".step-note");
    const note4 = tab4.querySelector(".step-note");
    tab3.classList.toggle("is-disabled", !visualAvailable);
    tab4.classList.toggle("is-disabled", !visualAvailable);
    if (note3) note3.textContent = visualAvailable ? "(activo)" : "(solo PDF)";
    if (note4) note4.textContent = visualAvailable ? "(activo)" : "(solo PDF)";
}

function updateStepUI() {
    for (let i = 0; i <= 5; i++) {
        const tab = document.getElementById("tab" + i);
        const pane = document.getElementById("step-" + i);
        tab.classList.toggle("active", i === currentStep);
        pane.classList.toggle("hidden", i !== currentStep);
    }
    document.getElementById("footerNav").classList.toggle("hidden", currentStep === 0);
    document.getElementById("btnPrev").classList.toggle("hidden", currentStep <= 1);

    const btnNext = document.getElementById("btnNext");
    if (currentStep === 5) {
        btnNext.classList.add("hidden");
        return;
    }
    btnNext.classList.remove("hidden");
    btnNext.disabled = false;
    if (currentStep === 2) {
        btnNext.textContent = visualAvailable ? "Siguiente: vista original" : "Ir a exportación";
        btnNext.disabled = findings.some(f => f.status === "pending");
    } else if (currentStep === 3) {
        btnNext.textContent = "Siguiente: aplicar sobre original";
    } else if (currentStep === 4) {
        btnNext.textContent = "Ir a exportación";
        btnNext.disabled = visualAvailable && (!appliedOriginal || applyingOriginal);
    } else {
        btnNext.textContent = "Siguiente";
    }
}

function goToStep(step) {
    currentStep = step;
    updateStepUI();
    if (step === 1) renderAnalysis();
    if (step === 2) renderReview();
    if (step === 3) renderVisualReview();
    if (step === 4) renderOriginalApplication();
    if (step === 5) renderExport();
}

function nextStep() {
    if (currentStep === 2 && !visualAvailable) {
        goToStep(5);
        return;
    }
    if (currentStep < 5) goToStep(currentStep + 1);
}

function prevStep() {
    if (currentStep === 5 && !visualAvailable) {
        goToStep(2);
        return;
    }
    if (currentStep > 1) goToStep(currentStep - 1);
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
}

// escapeHtml (textContent -> innerHTML) does not escape quotes, so it is not
// safe inside attribute values. Use escapeAttr for anything placed in "...".
function escapeAttr(text) {
    return String(text ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

async function cleanupVisualSession() {
    if (!visualSession) return;
    try {
        await apiFetch("/api/session/cleanup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: visualSession })
        });
    } catch (_) { }
    visualSession = null;
    visualPages = [];
    visualAvailable = false;
    visualMode = null;
    visualOcrUsed = false;
    visualReason = "";
    appliedOriginal = null;
    appliedSignature = null;
    applyingOriginal = false;
    setStepLabels();
}

function onTextChange() {
    const value = document.getElementById("textInput").value;
    document.getElementById("charCount").textContent = value ? `${value.length} caracteres` : "";
    document.getElementById("btnAnalyze").disabled = !value.trim() && !selectedFile;
}

function onFileSelected() {
    const input = document.getElementById("fileInput");
    if (!input.files.length) return;
    selectedFile = input.files[0];
    document.getElementById("uploadArea").classList.add("has-file");
    const fileName = document.getElementById("fileName");
    fileName.style.display = "block";
    fileName.textContent = selectedFile.name;
    document.getElementById("btnAnalyze").disabled = false;
}

function loadSample() {
    document.getElementById("textInput").value = SAMPLE_TEXT;
    selectedFile = null;
    document.getElementById("fileInput").value = "";
    document.getElementById("uploadArea").classList.remove("has-file");
    document.getElementById("fileName").style.display = "none";
    onTextChange();
}

async function analyze() {
    const btn = document.getElementById("btnAnalyze");
    btn.disabled = true;
    btn.textContent = "Analizando...";

    await cleanupVisualSession();

    try {
        let response;
        if (selectedFile) {
            const fd = new FormData();
            fd.append("file", selectedFile);
            response = await apiFetch("/api/analyze/file", { method: "POST", body: fd });
        } else {
            response = await apiFetch("/api/analyze/text", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: document.getElementById("textInput").value })
            });
        }
        const data = await response.json();
        if (!response.ok || data.error) throw new Error(data.error || "No se pudo analizar el documento.");

        documentText = data.text;
        findings = data.findings || [];
        findingCounter = findings.length;
        layersActive = data.layers_active || ["regex"];
        layersAvailable = data.layers_available || ["regex"];
        currentFormat = data.format || "txt";
        visualSession = data.visual_session || null;
        visualPages = data.visual_pages || [];
        visualAvailable = Boolean(data.visual_available && visualSession && visualPages.length);
        visualMode = data.visual_mode || null;
        visualOcrUsed = Boolean(data.visual_ocr_used);
        visualReason = data.visual_reason || "";
        appliedOriginal = null;
        appliedSignature = null;
        applyingOriginal = false;
        setStepLabels();

        goToStep(1);
        setTimeout(() => goToStep(2), 700);
    } catch (err) {
        alert("Error: " + err.message);
    } finally {
        btn.textContent = "Analizar";
        btn.disabled = false;
    }
}

function renderAnalysis() {
    const categories = {};
    findings.forEach(f => {
        if (!categories[f.category]) categories[f.category] = 0;
        categories[f.category] += 1;
    });
    const categoryCount = Object.keys(categories).length;
    document.getElementById("analysisSummary").innerHTML = `Se han detectado <strong>${findings.length}</strong> hallazgos en <strong>${categoryCount}</strong> categorías.`;
    let cards = "";
    Object.keys(categories).forEach(cat => {
        const color = CATEGORY_COLORS[cat] || "#6B7280";
        cards += `<div class="stat-card"><div class="num" style="color:${color}">${categories[cat]}</div><div class="lbl">${catLabel(cat)}</div></div>`;
    });
    document.getElementById("summaryCards").innerHTML = cards || `<div class="stat-card"><div class="num">0</div><div class="lbl">Sin hallazgos</div></div>`;
    let meta = `Formato de trabajo: <strong>${escapeHtml(currentFormat.toUpperCase())}</strong>. Capas activas: <strong>${escapeHtml(layersActive.join(", "))}</strong>.`;
    if (visualAvailable) {
        meta += ` Revisión visual disponible para PDF original. Base utilizada: <strong>${escapeHtml(visualMode || "text_layer")}</strong>.`;
    }
    document.getElementById("analysisMeta").innerHTML = meta;
}

function renderHighlightedDoc() {
    const activeFindings = findings.filter(f => f.status !== "discarded").sort((a, b) => a.position.start - b.position.start);
    let html = "";
    let last = 0;
    for (const finding of activeFindings) {
        if (finding.position.start > last) html += escapeHtml(documentText.slice(last, finding.position.start));
        const color = CATEGORY_COLORS[finding.category] || "#6B7280";
        const opacity = finding.status === "confirmed" ? "35" : "18";
        html += `<mark class="pii-mark" style="background:${color}${opacity};border-bottom:2px solid ${color};" title="${escapeAttr(finding.label)}">${escapeHtml(documentText.slice(finding.position.start, finding.position.end))}</mark>`;
        last = finding.position.end;
    }
    if (last < documentText.length) html += escapeHtml(documentText.slice(last));
    document.getElementById("docView").innerHTML = html;
}

function renderFindingsList() {
    let html = "";
    for (const finding of findings) {
        const color = CATEGORY_COLORS[finding.category] || "#6B7280";
        const discarded = finding.status === "discarded";
        const confirmed = finding.status === "confirmed";
        let actions = "";
        if (!discarded && !confirmed) {
            actions = `<button class="btn btn-sm" data-action="setStatus" data-id="${escapeAttr(finding.id)}" data-status="confirmed">Confirmar</button><button class="btn btn-sm" data-action="setStatus" data-id="${escapeAttr(finding.id)}" data-status="discarded">Descartar</button>`;
        } else if (confirmed) {
            actions = `<button class="btn btn-sm" data-action="setStatus" data-id="${escapeAttr(finding.id)}" data-status="discarded">Descartar</button>`;
        } else {
            actions = `<button class="btn btn-sm" data-action="setStatus" data-id="${escapeAttr(finding.id)}" data-status="pending">Restaurar</button>`;
        }
        html += `<div class="finding-card ${discarded ? 'discarded' : ''}">
    <div class="finding-meta">
        <span class="finding-badge" style="background:${color}18;color:${color};">${escapeHtml(finding.label)}</span>
        <span class="finding-id">${escapeHtml(finding.id)}</span>
        <span class="finding-status">${escapeHtml(finding.status.toUpperCase())}</span>
        ${finding.method === 'manual' ? '<span class="finding-status" style="color:var(--accent)">MANUAL</span>' : ''}
    </div>
    <div class="finding-text">${escapeHtml(finding.text)}</div>
    <div class="finding-actions">${actions}</div>
    ${confirmed ? `<select data-change="setTechnique" data-id="${escapeAttr(finding.id)}">
        <option value="suppression" ${finding.technique === 'suppression' ? 'selected' : ''}>Supresión</option>
        <option value="generalization" ${finding.technique === 'generalization' ? 'selected' : ''}>Generalización</option>
        <option value="pseudonymization" ${finding.technique === 'pseudonymization' ? 'selected' : ''}>Seudonimización</option>
    </select>` : ''}
</div>`;
    }
    document.getElementById("findingsList").innerHTML = html;
}

function updateReviewStats() {
    const pending = findings.filter(f => f.status === "pending").length;
    const confirmed = findings.filter(f => f.status === "confirmed").length;
    const discarded = findings.filter(f => f.status === "discarded").length;
    document.getElementById("reviewCounters").innerHTML = `<strong>${pending}</strong> pendientes · <strong>${confirmed}</strong> confirmados · <strong>${discarded}</strong> descartados`;
    updateStepUI();
}

function renderReview() {
    renderHighlightedDoc();
    renderFindingsList();
    updateReviewStats();
    const hint = document.getElementById("workflowHint");
    if (visualAvailable) {
        hint.innerHTML = "<strong>Flujo adicional activo:</strong> este PDF dispone del paso 4 «Vista original PDF» y del paso 5 «Aplicación sobre el original» antes de la exportación.";
    } else if (currentFormat === "pdf") {
        const reasonText = visualReason ? ` ${escapeHtml(visualReason)}` : "";
        hint.innerHTML = `<strong>Flujo visual no disponible:</strong> el documento es PDF, pero en esta sesión no se ha podido activar la revisión visual basada en imagen original.${reasonText} La exportación seguirá siendo textual.`;
    } else {
        hint.innerHTML = "<strong>Flujo aplicable:</strong> los pasos de vista original y aplicación sobre el original solo se activan cuando el documento de entrada es un PDF y hay revisión visual disponible.";
    }
}

function setStatus(id, status) {
    findings = findings.map(f => {
        if (f.id !== id) return f;
        const updated = { ...f, status };
        if (status === "confirmed" && !updated.technique) updated.technique = "suppression";
        return updated;
    });
    renderReview();
}

function setTechnique(id, technique) {
    findings = findings.map(f => f.id === id ? { ...f, technique } : f);
}

function confirmAll() {
    findings = findings.map(f => f.status === "pending" ? { ...f, status: "confirmed", technique: f.technique || "suppression" } : f);
    renderReview();
}

function getSelectionOffsets(root, range) {
    const preRange = range.cloneRange();
    preRange.selectNodeContents(root);
    preRange.setEnd(range.startContainer, range.startOffset);
    const start = preRange.toString().length;
    return { start, end: start + range.toString().length };
}

function onDocSelection() {
    if (currentStep !== 2) return;
    const docView = document.getElementById("docView");
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) return;
    const range = selection.getRangeAt(0);
    if (!docView.contains(range.commonAncestorContainer)) return;
    const selectedText = selection.toString().trim();
    if (selectedText.length < 2) return;
    const offsets = getSelectionOffsets(docView, range);
    const overlaps = findings.some(f => f.status !== "discarded" && !(offsets.end <= f.position.start || offsets.start >= f.position.end));
    if (overlaps) return;
    manualSelection = { text: documentText.slice(offsets.start, offsets.end), start: offsets.start, end: offsets.end };
    document.getElementById("popupSelectedText").textContent = manualSelection.text;
    let options = "";
    Object.keys(CATEGORY_COLORS).forEach(cat => {
        options += `<span class="cat-opt ${cat === manualCategory ? 'selected' : ''}" style="background:${CATEGORY_COLORS[cat]}18;color:${CATEGORY_COLORS[cat]};" data-action="selectCategory" data-category="${escapeAttr(cat)}">${catLabel(cat)}</span>`;
    });
    document.getElementById("categoryOptions").innerHTML = options;
    const popup = document.getElementById("selectionPopup");
    const rect = range.getBoundingClientRect();
    popup.style.left = Math.min(rect.left, window.innerWidth - 320) + "px";
    popup.style.top = (rect.bottom + 8) + "px";
    popup.classList.add("visible");
}

function selectCategory(category, element) {
    manualCategory = category;
    document.querySelectorAll('.cat-opt').forEach(el => el.classList.remove('selected'));
    element.classList.add('selected');
}

function addManualFinding() {
    if (!manualSelection) return;
    findingCounter += 1;
    findings.push({
        id: "m" + String(findingCounter).padStart(3, "0"),
        text: manualSelection.text,
        category: manualCategory,
        type: "manual_" + manualCategory,
        label: catLabel(manualCategory),
        description: "Marcado manual",
        position: { start: manualSelection.start, end: manualSelection.end },
        confidence: 1.0,
        method: "manual",
        status: "confirmed",
        technique: "suppression"
    });
    findings.sort((a, b) => a.position.start - b.position.start);
    hidePopup();
    window.getSelection().removeAllRanges();
    renderReview();
}

function hidePopup() {
    document.getElementById("selectionPopup").classList.remove("visible");
    manualSelection = null;
}

function rectanglesForPage(page) {
    const confirmed = findings.filter(f => f.status === "confirmed");
    const grouped = {};
    for (const finding of confirmed) {
        const overlaps = (page.words || []).filter(word => !(finding.position.end <= word.start || finding.position.start >= word.end));
        overlaps.forEach(word => {
            const key = finding.id + "::" + word.line_key;
            if (!grouped[key]) grouped[key] = [];
            grouped[key].push(word.bbox);
        });
    }
    return Object.values(grouped).map(boxes => {
        const x0 = Math.min(...boxes.map(b => b[0])) - 2;
        const y0 = Math.min(...boxes.map(b => b[1])) - 1;
        const x1 = Math.max(...boxes.map(b => b[2])) + 2;
        const y1 = Math.max(...boxes.map(b => b[3])) + 1;
        return { left: Math.max(0, x0), top: Math.max(0, y0), width: x1 - x0, height: y1 - y0 };
    });
}

function renderVisualReview() {
    if (!visualAvailable) {
        goToStep(4);
        return;
    }
    document.getElementById("visualModeBox").innerHTML = `<strong>Base de alineación:</strong> ${visualMode === 'ocr' ? 'OCR sobre imagen renderizada' : visualMode === 'hybrid' ? 'Capa de texto + OCR' : 'Capa de texto del PDF'}${visualOcrUsed ? ' (OCR usado en al menos una página)' : ''}.`;
    document.getElementById("visualHelpBox").innerHTML = `<strong>Qué se ve aquí:</strong> la proyección previa de las máscaras sobre la imagen original. En el siguiente paso se materializa la edición y se genera la copia redactada del original.`;
    let html = "";
    for (const page of visualPages) {
        const rects = rectanglesForPage(page);
        const overlays = rects.map(rect => `<div class="redaction-box" style="left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px;"></div>`).join("");
        html += `<div class="visual-page">
    <div class="visual-page-header">
        <div><strong>Página ${page.page}</strong></div>
        <div style="font-size:12px;color:var(--text-2);">Fuente: ${page.source}</div>
    </div>
    <div class="visual-stage">
        <div class="page-canvas" style="width:${page.width}px;">
            <img src="${page.image_url}" alt="Página ${page.page}">
            ${overlays}
        </div>
    </div>
    <div style="font-size:12px;color:var(--text-2);margin-top:10px;">Máscaras visibles en esta página: <strong>${rects.length}</strong>.</div>
</div>`;
    }
    document.getElementById("visualPages").innerHTML = html;
}

function confirmedFindingsSignature() {
    const confirmed = findings
        .filter(f => f.status === "confirmed")
        .map(f => ({ id: f.id, start: f.position.start, end: f.position.end, technique: f.technique || "suppression" }))
        .sort((a, b) => (a.start - b.start) || a.id.localeCompare(b.id));
    return JSON.stringify(confirmed);
}

function renderAppliedOriginalPages() {
    const container = document.getElementById("appliedOriginalPages");
    if (!appliedOriginal || !(appliedOriginal.pages || []).length) {
        container.innerHTML = "";
        return;
    }
    let html = "";
    for (const page of appliedOriginal.pages) {
        html += `<div class="visual-page">
    <div class="visual-page-header">
        <div><strong>Página ${page.page}</strong></div>
        <div style="font-size:12px;color:var(--text-2);">Redacciones aplicadas: ${page.rectangles}</div>
    </div>
    <div class="visual-stage">
        <div class="page-canvas" style="width:${page.width}px;">
            <img src="${page.image_url}" alt="Página ${page.page} editada">
        </div>
    </div>
</div>`;
    }
    container.innerHTML = html;
}

function renderOriginalApplication() {
    if (!visualAvailable) {
        goToStep(5);
        return;
    }
    const confirmed = findings.filter(f => f.status === "confirmed").length;
    document.getElementById("applyOriginalSummary").innerHTML = `<strong>Hallazgos confirmados:</strong> ${confirmed}. <strong>Páginas del original:</strong> ${visualPages.length}. <strong>Base de alineación:</strong> ${visualMode === 'ocr' ? 'OCR' : visualMode === 'hybrid' ? 'capa de texto + OCR' : 'capa de texto del PDF'}.`;
    if (!confirmed) {
        document.getElementById("applyOriginalStatus").innerHTML = "No hay hallazgos confirmados. Confirme al menos uno para aplicar la edición sobre el original.";
        document.getElementById("btnApplyOriginal").disabled = true;
        document.getElementById("appliedOriginalPages").innerHTML = "";
        appliedOriginal = null;
        appliedSignature = null;
        updateStepUI();
        return;
    }
    document.getElementById("btnApplyOriginal").disabled = applyingOriginal;
    if (appliedOriginal) {
        document.getElementById("applyOriginalStatus").innerHTML = `La edición ya se ha aplicado sobre una copia derivada del original. Páginas generadas: <strong>${appliedOriginal.page_count}</strong>. Máscaras materializadas: <strong>${appliedOriginal.total_rectangles}</strong>.`;
        renderAppliedOriginalPages();
    } else {
        document.getElementById("applyOriginalStatus").innerHTML = "La copia derivada todavía no se ha generado. Use el botón para aplicar la edición sobre el original de forma explícita.";
        document.getElementById("appliedOriginalPages").innerHTML = "";
    }
    updateStepUI();
}

async function applyOriginalEdits(button) {
    if (!visualAvailable || !visualSession) return;
    const signature = confirmedFindingsSignature();
    if (appliedOriginal && appliedSignature === signature) {
        renderOriginalApplication();
        return;
    }
    applyingOriginal = true;
    if (button) {
        button.disabled = true;
        button.textContent = "Aplicando...";
    }
    updateStepUI();
    try {
        const response = await apiFetch("/api/session/apply-original", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: visualSession, findings })
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || "No se pudo aplicar la edición sobre el original.");
        appliedOriginal = data.applied;
        appliedSignature = signature;
        renderOriginalApplication();
    } catch (err) {
        appliedOriginal = null;
        appliedSignature = null;
        document.getElementById("applyOriginalStatus").innerHTML = `<span style="color:var(--danger)">Error:</span> ${escapeHtml(err.message)}`;
        document.getElementById("appliedOriginalPages").innerHTML = "";
        updateStepUI();
    } finally {
        applyingOriginal = false;
        if (button) {
            button.disabled = false;
            button.textContent = "Aplicar edición sobre el original";
        }
        updateStepUI();
    }
}

function buildEnvelope() {
    const now = new Date().toISOString();
    const confirmed = findings.filter(f => f.status === "confirmed");
    const discarded = findings.filter(f => f.status === "discarded");
    return {
        document_id: "DOC-" + Date.now().toString(36).toUpperCase(),
        analysis_date: now,
        tool: "velo",
        version: APP_VERSION,
        layers_active: layersActive,
        layers_available: layersAvailable,
        source_format: currentFormat,
        visual_review: visualAvailable ? {
            session_active: true,
            mode: visualMode,
            page_count: visualPages.length,
            based_on_original_pdf_images: true
        } : {
            session_active: false,
            based_on_original_pdf_images: false
        },
        original_application: visualAvailable ? {
            generated: Boolean(appliedOriginal),
            page_count: appliedOriginal ? appliedOriginal.page_count : 0,
            total_rectangles: appliedOriginal ? appliedOriginal.total_rectangles : 0,
            based_on_ocr_or_text_layer: true
        } : {
            generated: false,
            based_on_ocr_or_text_layer: false
        },
        normative_framework: {
            redaction: "ISO/IEC 27038",
            anonymization_techniques: "ISO/IEC 20889",
            reidentification_risk: "ISO/IEC 27559",
            privacy_framework: "ISO/IEC 29100",
            privacy_management: "ISO/IEC 27701"
        },
        findings: confirmed.map(f => ({
            id: f.id,
            text: f.text,
            category: f.category,
            type: f.type,
            label: f.label,
            position: f.position,
            confidence: f.confidence,
            method: f.method,
            human_decision: "confirmed",
            technique: f.technique || "suppression"
        })),
        discarded: discarded.map(f => ({ id: f.id, text: f.text, type: f.type, reason: "false_positive" })),
        summary: {
            total_detected: findings.length,
            confirmed: confirmed.length,
            discarded: discarded.length,
            categories_found: [...new Set(confirmed.map(f => f.category))],
            types_found: [...new Set(confirmed.map(f => f.type))]
        },
        audit: {
            reviewed_by: "archivero",
            review_date: now.split("T")[0],
            tool_version: APP_VERSION,
            execution: "local"
        }
    };
}

function assessRisk(confirmed) {
    let direct = 0;
    let quasi = 0;
    confirmed.forEach(f => {
        if (["dni", "nie", "nss", "email", "iban"].includes(f.type)) direct += 1;
        if (["person_name", "address", "phone", "date_birth", "postal_code", "location"].includes(f.type)) quasi += 1;
    });
    let level = "ALTO";
    let text = "No se ha confirmado ningún dato sensible. Revise el documento antes de exportar.";
    let color = "#DC2626";
    if (confirmed.length >= 3) {
        level = "BAJO";
        text = `Se han tratado ${confirmed.length} hallazgos. Verifique que los datos residuales no permitan reidentificación por combinación.`;
        color = "#15803D";
    } else if (confirmed.length > 0) {
        level = "MEDIO";
        text = "Se han confirmado pocos hallazgos. Revise si quedan datos no marcados, especialmente cuasi-identificadores.";
        color = "#D97706";
    }
    document.getElementById("riskAssessment").innerHTML = `<div style="font-weight:800;margin-bottom:10px;">ISO/IEC 27559 — Riesgo de reidentificación</div>
<div style="display:inline-block;padding:4px 12px;border-radius:999px;background:${color}18;color:${color};font-size:11px;font-weight:800;margin-bottom:10px;">${level}</div>
<div style="color:var(--text-2);line-height:1.55;">${text}</div>
<div style="font-size:12px;color:var(--text-3);margin-top:8px;">Identificadores directos tratados: ${direct} · Cuasi-identificadores tratados: ${quasi}</div>`;
}

function renderExport() {
    const confirmed = findings.filter(f => f.status === "confirmed");
    const discarded = findings.filter(f => f.status === "discarded");
    document.getElementById("exportSummary").innerHTML = `${confirmed.length} confirmados · ${discarded.length} descartados.${visualAvailable ? (appliedOriginal ? ' La copia editada del original está lista para descarga.' : ' Puede generarse una copia editada del original antes de exportar.') : ''}`;
    document.getElementById("exportStats").innerHTML = `
<div class="stat-card"><div class="num" style="color:var(--confirm)">${confirmed.length}</div><div class="lbl">Confirmados</div></div>
<div class="stat-card"><div class="num">${discarded.length}</div><div class="lbl">Descartados</div></div>
<div class="stat-card"><div class="num">${[...new Set(confirmed.map(f => f.type))].length}</div><div class="lbl">Tipos</div></div>`;
    assessRisk(confirmed);
    document.getElementById("jsonOutput").textContent = JSON.stringify(buildEnvelope(), null, 2);
    document.getElementById("chkPurpose").checked = false;
    document.getElementById("chkReview").checked = false;
    document.getElementById("chkRisk").checked = false;
    document.getElementById("btnAppliedPdf").classList.toggle("hidden", !visualAvailable);
    document.getElementById("btnNativePdf").classList.toggle("hidden", !visualAvailable || !nativeRedactionAvailable);
    checkCompliance();
}

function checkCompliance() {
    const ok = document.getElementById("chkPurpose").checked && document.getElementById("chkReview").checked && document.getElementById("chkRisk").checked;
    const hasConfirmed = findings.some(f => f.status === "confirmed");
    document.getElementById("btnSave").disabled = !ok;
    document.getElementById("btnDerivedPdf").disabled = !ok;
    document.getElementById("btnAppliedPdf").disabled = !ok || (visualAvailable && !appliedOriginal);
    document.getElementById("btnNativePdf").disabled = !ok || !visualAvailable || !nativeRedactionAvailable || !hasConfirmed;
}

async function saveJSON(button) {
    try {
        const envelope = buildEnvelope();
        const response = await apiFetch("/api/export", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                document_id: envelope.document_id,
                findings: findings,
                layers_active: layersActive,
                layers_available: layersAvailable
            })
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || "No se pudo guardar el informe.");
        const original = button.textContent;
        button.textContent = "Guardado";
        setTimeout(() => button.textContent = original, 1400);
    } catch (err) {
        alert("Error: " + err.message);
    }
}

function copyJSON(button) {
    navigator.clipboard.writeText(document.getElementById("jsonOutput").textContent).then(() => {
        const original = button.textContent;
        button.textContent = "Copiado";
        setTimeout(() => button.textContent = original, 1200);
    });
}

const pseudoMap = {};
function replacementFor(finding) {
    const technique = finding.technique || "suppression";
    if (technique === "suppression") return "[DATO SUPRIMIDO]";
    if (technique === "generalization") {
        const labels = { person_name: "[PERSONA]", dni: "[DOC. ID]", nie: "[DOC. ID]", phone: "[TEL]", email: "[EMAIL]", iban: "[IBAN]", address: "[DIRECCIÓN]", date_birth: "[FECHA NAC.]" };
        return labels[finding.type] || `[${finding.label.toUpperCase()}]`;
    }
    const key = finding.type + "::" + finding.text;
    if (!pseudoMap[key]) pseudoMap[key] = `${finding.label} ${Object.keys(pseudoMap).length + 1}`;
    return pseudoMap[key];
}

function exportDerivedPDF() {
    Object.keys(pseudoMap).forEach(k => delete pseudoMap[k]);
    const confirmed = findings.filter(f => f.status === "confirmed").sort((a, b) => a.position.start - b.position.start);
    let html = "";
    let last = 0;
    confirmed.forEach(f => {
        if (f.position.start > last) html += escapeHtml(documentText.slice(last, f.position.start));
        html += `<span style="background:#000;color:#fff;padding:1px 6px;border-radius:2px;font-size:11px;font-weight:700;">${escapeHtml(replacementFor(f))}</span>`;
        last = f.position.end;
    });
    if (last < documentText.length) html += escapeHtml(documentText.slice(last));
    const win = window.open("", "_blank");
    win.document.write(`<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Documento testado</title><style>body{font-family:Courier New,monospace;font-size:12px;line-height:1.8;max-width:820px;margin:40px auto;padding:20px;color:#000}.doc{white-space:pre-wrap;word-break:break-word}.hdr,.ftr{font-family:Arial,sans-serif;font-size:11px;color:#666}.hdr{border-bottom:2px solid #000;padding-bottom:12px;margin-bottom:24px}.ftr{border-top:1px solid #ccc;padding-top:12px;margin-top:24px}@media print{.np{display:none}}</style></head><body><div class="hdr"><h2>DOCUMENTO TESTADO</h2><div>Velo v${APP_VERSION}</div><div>Copia derivada con sustituciones textuales</div></div><div class="doc">${html}</div><div class="ftr">El original no se ha modificado. Esta salida textual es una copia derivada.</div><div class="np" style="text-align:center;margin-top:24px;"><button id="printBtn" type="button" style="padding:10px 24px;border:0;border-radius:8px;background:#1c1917;color:#fff;cursor:pointer;">Imprimir / Guardar como PDF</button></div></body></html>`);
    win.document.close();
    const printBtn = win.document.getElementById("printBtn");
    if (printBtn) printBtn.addEventListener("click", () => win.print());
}

async function downloadAppliedOriginal(button) {
    if (!visualSession) return;
    if (!appliedOriginal) {
        alert("Primero hay que aplicar la edición sobre el original.");
        return;
    }
    try {
        const response = await apiFetch(`/api/session/${visualSession}/applied-original-pdf`);
        if (!response.ok) {
            let message = "No se pudo descargar el original editado.";
            try {
                const data = await response.json();
                if (data.error) message = data.error;
            } catch (_) { }
            throw new Error(message);
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `DOC-${Date.now().toString(36).toUpperCase()}_original_editado.pdf`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        const original = button.textContent;
        button.textContent = "Descargado";
        setTimeout(() => button.textContent = original, 1400);
    } catch (err) {
        alert("Error: " + err.message);
    }
}

async function downloadNativeRedactedPdf(button) {
    if (!visualSession || !nativeRedactionAvailable) return;
    if (!findings.some(f => f.status === "confirmed")) {
        alert("Confirme al menos un hallazgo antes de generar el expurgo nativo.");
        return;
    }

    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Expurgando...";
    try {
        const documentId = `DOC-${Date.now().toString(36).toUpperCase()}`;
        const response = await apiFetch("/api/export/redacted-pdf", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: visualSession,
                document_id: documentId,
                findings,
                redaction_mode: "native"
            })
        });
        if (!response.ok) {
            let message = "No se pudo generar el PDF con expurgo nativo.";
            try {
                const data = await response.json();
                if (data.error) message = data.error;
            } catch (_) { }
            throw new Error(message);
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${documentId}_native_redacted.pdf`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
        button.textContent = "Descargado";
        setTimeout(() => button.textContent = original, 1400);
    } catch (err) {
        button.textContent = original;
        alert("Error: " + err.message);
    } finally {
        button.disabled = false;
        checkCompliance();
    }
}

async function resetAll() {
    await cleanupVisualSession();
    currentStep = 0;
    documentText = "";
    findings = [];
    layersActive = [];
    layersAvailable = [];
    selectedFile = null;
    manualSelection = null;
    findingCounter = 0;
    currentFormat = "txt";
    appliedOriginal = null;
    appliedSignature = null;
    applyingOriginal = false;
    document.getElementById("textInput").value = "";
    document.getElementById("fileInput").value = "";
    document.getElementById("uploadArea").classList.remove("has-file");
    document.getElementById("fileName").style.display = "none";
    document.getElementById("summaryCards").innerHTML = "";
    document.getElementById("findingsList").innerHTML = "";
    document.getElementById("docView").innerHTML = "";
    document.getElementById("visualPages").innerHTML = "";
    document.getElementById("appliedOriginalPages").innerHTML = "";
    document.getElementById("applyOriginalSummary").innerHTML = "";
    document.getElementById("applyOriginalStatus").innerHTML = "";
    document.getElementById("jsonOutput").textContent = "";
    setStepLabels();
    onTextChange();
    goToStep(0);
}

function shutdownServer() {
    if (!confirm("Se va a apagar Velo. Los datos no guardados se perderán.\n\n¿Desea continuar?")) return;
    apiFetch("/api/shutdown", { method: "POST" }).finally(() => {
        document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:Segoe UI,system-ui,sans-serif;"><div><h2>Velo se ha apagado</h2><p style="color:#57534E">Puede cerrar esta ventana.</p></div></div>';
    });
}

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("textInput").addEventListener("input", onTextChange);
    document.getElementById("fileInput").addEventListener("change", onFileSelected);
    const uploadArea = document.getElementById("uploadArea");
    uploadArea.addEventListener("dragover", event => { event.preventDefault(); uploadArea.style.borderColor = "var(--accent)"; });
    uploadArea.addEventListener("dragleave", () => { uploadArea.style.borderColor = ""; });
    uploadArea.addEventListener("drop", event => {
        event.preventDefault();
        uploadArea.style.borderColor = "";
        if (event.dataTransfer.files.length) {
            document.getElementById("fileInput").files = event.dataTransfer.files;
            onFileSelected();
        }
    });
    document.addEventListener("mouseup", onDocSelection);
    document.addEventListener("click", event => {
        const popup = document.getElementById("selectionPopup");
        if (!popup.contains(event.target) && !event.target.closest(".doc-view")) hidePopup();
    });
    apiFetch("/api/status")
        .then(r => r.json())
        .then(d => {
            let label = "LOCAL";
            if (d.layers && d.layers.spacy && d.layers.spacy_model) label += " + NER";
            if (d.visual_redaction && d.visual_redaction.implemented) label += " + PDF";
            nativeRedactionAvailable = Boolean(d.visual_redaction && d.visual_redaction.modes && d.visual_redaction.modes.native);
            if (nativeRedactionAvailable) label += " + EXPURGO";
            document.getElementById("statusLabel").textContent = label;
        })
        .catch(() => { });
    setStepLabels();
    updateStepUI();
});

// ---------------------------------------------------------------------------
// Event delegation. The CSP allows only script-src 'self', so the page has no
// inline handlers: elements declare data-action / data-change and these
// allowlists map them to functions. Unknown names are ignored.
// ---------------------------------------------------------------------------
const CLICK_ACTIONS = {
    shutdownServer: () => shutdownServer(),
    openFilePicker: () => document.getElementById("fileInput").click(),
    loadSample: () => loadSample(),
    analyze: () => analyze(),
    confirmAll: () => confirmAll(),
    applyOriginalEdits: el => applyOriginalEdits(el),
    copyJSON: el => copyJSON(el),
    saveJSON: el => saveJSON(el),
    exportDerivedPDF: () => exportDerivedPDF(),
    downloadAppliedOriginal: el => downloadAppliedOriginal(el),
    downloadNativeRedactedPdf: el => downloadNativeRedactedPdf(el),
    resetAll: () => resetAll(),
    prevStep: () => prevStep(),
    nextStep: () => nextStep(),
    addManualFinding: () => addManualFinding(),
    hidePopup: () => hidePopup(),
    setStatus: el => setStatus(el.dataset.id, el.dataset.status),
    selectCategory: el => selectCategory(el.dataset.category, el),
};

const CHANGE_ACTIONS = {
    checkCompliance: () => checkCompliance(),
    setTechnique: el => setTechnique(el.dataset.id, el.value),
};

document.addEventListener("click", event => {
    const el = event.target.closest("[data-action]");
    if (!el || el.disabled) return;
    const handler = Object.prototype.hasOwnProperty.call(CLICK_ACTIONS, el.dataset.action) && CLICK_ACTIONS[el.dataset.action];
    if (handler) handler(el);
});

document.addEventListener("change", event => {
    const el = event.target.closest("[data-change]");
    if (!el) return;
    const handler = Object.prototype.hasOwnProperty.call(CHANGE_ACTIONS, el.dataset.change) && CHANGE_ACTIONS[el.dataset.change];
    if (handler) handler(el);
});

// Images that should disappear if they fail to load (the logo).
document.querySelectorAll("img[data-hide-on-error]").forEach(img => {
    const hide = () => { img.style.display = "none"; };
    if (img.complete && img.naturalWidth === 0) hide();
    else img.addEventListener("error", hide);
});
