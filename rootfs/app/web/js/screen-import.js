// screen-import.js — Import YAML screen logic
// Depends on window.AirSend (populated by the main inline script before this file runs)
(function () {
  "use strict";

  var ns = window.AirSend;
  var t            = ns.t;
  var api          = ns.api;
  var $            = ns.$;
  var show         = ns.show;
  var hide         = ns.hide;
  var escapeAttr   = ns.escapeAttr;
  var backToHome   = ns.backToHome;
  var state        = ns.state;
  var KIND_LABEL_KEYS  = ns.KIND_LABEL_KEYS;
  var DOMAIN_TO_KINDS  = ns.DOMAIN_TO_KINDS;

  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------
  var currentImportRows = [];
  var detectedYamlText  = null;

  // Expose so the main script's refreshDynamicUi() can call renderImportTable()
  ns.getImportRows    = function () { return currentImportRows; };
  ns.renderImportTable = renderImportTable;

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------
  function resetImportScreen() {
    currentImportRows = [];
    detectedYamlText  = null;
    $("import-yaml-textarea").value = "";
    $("import-file-input").value    = "";
    hide("import-error");
    hide("import-detect-banner");
    hide("import-step-preview");
    show("import-step-input");
    $("import-table-body").innerHTML = "";
    hide("import-result");
  }

  function detectImportFile() {
    api("api/import/detect").then(function (res) {
      if (!res.ok || !res.body.found) return;
      detectedYamlText = res.body.yaml_text;
      $("import-detect-text").textContent = t("import.detected", { path: res.body.path });
      show("import-detect-banner");
    });
  }

  function domainSelectHtml(row) {
    var opts = Object.keys(DOMAIN_TO_KINDS).map(function (d) {
      return "<option value='" + d + "'" + (row.domain === d ? " selected" : "") + ">" + d + "</option>";
    }).join("");
    var label = t("import.domainAriaLabel", { name: escapeAttr(row.friendly_name) });
    return "<select data-field='domain' aria-label='" + label + "'><option value=''>--</option>" + opts + "</select>";
  }

  function kindSelectHtml(row) {
    var kinds = row.domain ? (DOMAIN_TO_KINDS[row.domain] || []) : [];
    var opts = kinds.map(function (k) {
      return "<option value='" + k + "'" + (row.kind === k ? " selected" : "") + ">" + t(KIND_LABEL_KEYS[k]) + "</option>";
    }).join("");
    var label = t("import.kindAriaLabel", { name: escapeAttr(row.friendly_name) });
    return "<select data-field='kind' aria-label='" + label + "'><option value=''>--</option>" + opts + "</select>";
  }

  function conflictFieldHtml(row) {
    if (row.status !== "conflict") return "<span class='muted'>–</span>";
    var label = t("import.conflictAriaLabel", { name: escapeAttr(row.friendly_name) });
    return "<select data-field='conflict_action' aria-label='" + label + "'>" +
      "<option value='keep_existing'>" + t("import.conflictKeepExisting") + "</option>" +
      "<option value='overwrite'>" + t("import.conflictOverwrite") + "</option>" +
      "</select>";
  }

  function importCountLabel(n, singularKey, pluralKey) {
    return t(n === 1 ? singularKey : pluralKey, { n: n });
  }

  function renderImportSummary() {
    var counts = { new: 0, conflict: 0, unknown_protocol: 0 };
    currentImportRows.forEach(function (row) {
      counts[row.status] = (counts[row.status] || 0) + 1;
    });
    var parts = [];
    if (counts.new)             parts.push(importCountLabel(counts.new,             "import.summary.newSingular",      "import.summary.newPlural"));
    if (counts.conflict)        parts.push(importCountLabel(counts.conflict,        "import.summary.conflictSingular", "import.summary.conflictPlural"));
    if (counts.unknown_protocol) parts.push(importCountLabel(counts.unknown_protocol, "import.summary.unknownSingular",  "import.summary.unknownPlural"));
    $("import-summary").textContent = parts.join(" · ");
  }

  function importRowFieldsHtml(row) {
    if (row.status === "unknown_protocol") {
      return (
        "<div class='import-field'><label>" + t("import.col.domain") + "</label><span class='muted'>–</span></div>" +
        "<div class='import-field'><label>" + t("import.col.kind") + "</label><span class='muted'>–</span></div>" +
        "<div class='import-field'><label>" + t("import.col.conflict") + "</label><span class='muted'>–</span></div>" +
        "<div class='import-note muted'>" + t("import.unknownProtocolNote") + "</div>"
      );
    }
    var translatedNote = row.kind_translated
      ? "<div class='muted' style='font-size:0.75em'>" + t("import.kindTranslatedNote") + "</div>" : "";
    return (
      "<div class='import-field'><label>" + t("import.col.domain") + "</label>" + domainSelectHtml(row) + "</div>" +
      "<div class='import-field'><label>" + t("import.col.kind") + "</label>" + kindSelectHtml(row) + translatedNote + "</div>" +
      "<div class='import-field'><label>" + t("import.col.conflict") + "</label>" + conflictFieldHtml(row) + "</div>"
    );
  }

  function renderImportTable() {
    renderImportSummary();
    $("import-table-body").innerHTML = currentImportRows.map(function (row, i) {
      var checked       = row.status !== "unknown_protocol" ? "checked" : "";
      var disabled      = row.status === "unknown_protocol" ? "disabled" : "";
      var checkboxLabel = t("import.checkboxAriaLabel", { name: escapeAttr(row.friendly_name) });
      var toggleLabel   = t(row.expanded ? "import.collapse" : "import.modify");
      var toggleAria    = t("import.toggleAriaLabel", { name: escapeAttr(row.friendly_name) });
      return "<div class='import-row status-" + row.status + (row.expanded ? " expanded" : "") + "' data-index='" + i + "'>" +
        "<div class='import-row-head'>" +
          "<label class='import-check-wrap'><input type='checkbox' class='import-check' aria-label='" + checkboxLabel + "' " + checked + " " + disabled + "></label>" +
          "<div class='import-row-main'>" +
            "<div class='import-row-name'>" + row.friendly_name + "</div>" +
            "<div class='import-row-sub'>" + row.key + "<span class='import-sub-protocol'> · " + row.protocol_name + "</span></div>" +
          "</div>" +
          "<div class='import-protocol'>" + row.protocol_name + "</div>" +
          "<span class='status-pill " + row.status + "'>" + row.status + "</span>" +
          "<button type='button' class='import-toggle' data-action='toggle' aria-label='" + toggleAria + "' aria-expanded='" + (row.expanded ? "true" : "false") + "'>" + toggleLabel + "</button>" +
        "</div>" +
        "<div class='import-details'>" + importRowFieldsHtml(row) + "</div>" +
      "</div>";
    }).join("");
  }

  // -----------------------------------------------------------------------
  // Event listeners
  // -----------------------------------------------------------------------
  $("btn-open-import").addEventListener("click", function () {
    resetImportScreen();
    detectImportFile();
  });

  window.AirSend.openImport = function () {
    resetImportScreen();
    detectImportFile();
  };

  $("import-detect-use-btn").addEventListener("click", function () {
    if (detectedYamlText === null) return;
    $("import-yaml-textarea").value = detectedYamlText;
    hide("import-detect-banner");
  });

  $("import-file-input").addEventListener("change", function () {
    var file = this.files[0];
    if (!file) return;
    file.text().then(function (text) { $("import-yaml-textarea").value = text; });
  });

  $("import-preview-btn").addEventListener("click", function () {
    hide("import-error");
    var yamlText = $("import-yaml-textarea").value;
    if (!yamlText.trim()) return;
    api("api/import/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ yaml_text: yamlText, box: state.box }),
    }).then(function (res) {
      if (!res.ok) {
        var err = $("import-error");
        err.textContent = res.body.text || res.body.error || t("import.parseError");
        show(err.id);
        return;
      }
      currentImportRows = res.body.rows.map(function (row) {
        row.expanded = row.status !== "new";
        return row;
      });
      renderImportTable();
      hide("import-step-input");
      show("import-step-preview");
    });
  });

  $("import-table-body").addEventListener("click", function (e) {
    var btn = e.target.closest(".import-toggle");
    if (!btn) return;
    var row = btn.closest(".import-row");
    var idx = Number.parseInt(row.dataset.index, 10);
    currentImportRows[idx].expanded = !currentImportRows[idx].expanded;
    renderImportTable();
  });

  $("import-table-body").addEventListener("change", function (e) {
    var row = e.target.closest(".import-row");
    if (!row) return;
    var idx   = Number.parseInt(row.dataset.index, 10);
    var field = e.target.dataset.field;
    if (!field) return;
    if (field === "conflict_action") {
      currentImportRows[idx].conflict_action = e.target.value;
      return;
    }
    currentImportRows[idx][field] = e.target.value;
    if (field === "domain") {
      currentImportRows[idx].kind = null;
      renderImportTable();
    }
  });

  $("import-commit-btn").addEventListener("click", function () {
    var checks = document.querySelectorAll(".import-check");
    var rowsToCommit = currentImportRows.map(function (row, i) {
      var checked = checks[i].checked;
      var action  = "skip";
      if (checked) {
        action = row.status === "conflict" ? (row.conflict_action || "keep_existing") : "import";
      }
      var copy = Object.assign({}, row);
      copy.action = action;
      return copy;
    });

    $("import-commit-btn").disabled = true;
    api("api/import/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows: rowsToCommit }),
    }).then(function (res) {
      $("import-commit-btn").disabled = false;
      var result = $("import-result");
      if (!res.ok) {
        result.className = "banner error";
        result.textContent = res.body.text || t("import.commitError");
        show(result.id);
        return;
      }
      var body = res.body;
      result.className = body.errors.length ? "banner warn" : "banner ok";
      result.textContent =
        t("import.resultSummary", { added: body.added, overwritten: body.overwritten, skipped: body.skipped }) +
        (body.errors.length ? t("import.resultErrors", { errors: body.errors.join(" | ") }) : "");
      show(result.id);
    });
  });

})();
