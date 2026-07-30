// screen-backup.js — Backup / restore screen logic
// Depends on window.AirSend (populated by the main inline script before this file runs)
(function () {
  "use strict";

  var ns = window.AirSend;
  var t          = ns.t;
  var api        = ns.api;
  var $          = ns.$;
  var show       = ns.show;
  var hide       = ns.hide;
  var escapeAttr = ns.escapeAttr;
  var backToHome = ns.backToHome;
  var boxesCache = ns.boxesCache;   // live reference — array is mutated in place by loadBoxes()

  // -----------------------------------------------------------------------
  // Constants
  // -----------------------------------------------------------------------
  var BACKUP_STATUS_LABEL_KEYS = {
    new:          "backup.status.new",
    identical:    "backup.status.identical",
    conflict:     "backup.status.conflict",
    unknown_box:  "backup.status.unknown_box",
    invalid_kind: "backup.status.invalid_kind",
  };

  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------
  var currentBackupRows   = [];
  var pendingBackupPayload = null;

  // Expose so the main script's refreshDynamicUi() can call renderBackupTable()
  ns.getBackupRows     = function () { return currentBackupRows; };
  ns.renderBackupTable = renderBackupTable;

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------
  function resetBackupScreen() {
    currentBackupRows    = [];
    pendingBackupPayload = null;
    $("backup-file-input").value       = "";
    $("backup-preview-btn").disabled   = true;
    hide("backup-error");
    hide("backup-step-preview");
    show("backup-step-input");
    $("backup-table-body").innerHTML = "";
    hide("backup-result");
  }

  function backupCountLabel(n, statusKey) {
    return t("backup.summary." + statusKey + (n === 1 ? "Singular" : "Plural"), { n: n });
  }

  function renderBackupSummary() {
    var counts = {};
    currentBackupRows.forEach(function (row) {
      counts[row.status] = (counts[row.status] || 0) + 1;
    });
    var parts = Object.keys(counts).map(function (status) {
      return backupCountLabel(counts[status], status);
    });
    $("backup-summary").textContent = parts.join(" · ");
  }

  function backupActionSelectHtml(row, index) {
    if (row.status === "invalid_kind") return "<span class='muted'>–</span>";

    if (row.status === "unknown_box") {
      var boxLabel = t("backup.boxSelectAriaLabel", { name: escapeAttr(row.friendly_name) });
      var boxOpts  = boxesCache.map(function (b) {
        return "<option value='" + b.slug + "'" + (row.box === b.slug ? " selected" : "") + ">" + b.slug + "</option>";
      }).join("");
      return "<select data-index='" + index + "' data-field='box' aria-label='" + boxLabel + "'>" +
        "<option value=''>" + t("backup.boxSelectPlaceholder") + "</option>" + boxOpts + "</select>";
    }

    var actionLabel = t("backup.actionAriaLabel", { name: escapeAttr(row.friendly_name) });
    var actions     = row.status === "conflict" ? ["skip", "overwrite"] : ["skip", "import"];
    var actionOpts  = actions.map(function (a) {
      return "<option value='" + a + "'" + (row.action === a ? " selected" : "") + ">" + t("backup.action." + a) + "</option>";
    }).join("");
    return "<select data-index='" + index + "' data-field='action' aria-label='" + actionLabel + "'>" + actionOpts + "</select>";
  }

  function renderBackupTable() {
    renderBackupSummary();
    $("backup-table-body").innerHTML = currentBackupRows.map(function (row, i) {
      var statusLabel = t(BACKUP_STATUS_LABEL_KEYS[row.status] || row.status);
      return "<div class='backup-row'>" +
        "<div class='backup-row-main'>" +
          "<div class='backup-row-name'>" + row.friendly_name + "</div>" +
          "<div class='backup-row-sub'>" + row.key + " · " + row.box + "</div>" +
        "</div>" +
        "<span class='status-pill " + row.status + "'>" + statusLabel + "</span>" +
        "<div class='backup-row-action'>" + backupActionSelectHtml(row, i) + "</div>" +
      "</div>";
    }).join("");
  }

  // -----------------------------------------------------------------------
  // Event listeners
  // -----------------------------------------------------------------------
  $("btn-open-backup").addEventListener("click", function () {
    resetBackupScreen();
    hide("screen-home");
    show("screen-backup");
  });

  $("btn-backup-cancel").addEventListener("click", backToHome);

  $("backup-file-input").addEventListener("change", function () {
    var file = this.files[0];
    pendingBackupPayload           = null;
    $("backup-preview-btn").disabled = true;
    hide("backup-error");
    if (!file) return;
    file.text().then(function (text) {
      try {
        pendingBackupPayload             = JSON.parse(text);
        $("backup-preview-btn").disabled = false;
      } catch (e) {
        var err = $("backup-error");
        err.textContent = t("backup.parseError");
        show(err.id);
      }
    });
  });

  $("backup-preview-btn").addEventListener("click", function () {
    hide("backup-error");
    if (!pendingBackupPayload) return;
    api("api/backup/import/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backup: pendingBackupPayload }),
    }).then(function (res) {
      if (!res.ok) {
        var err = $("backup-error");
        err.textContent = res.body.text || res.body.error || t("backup.parseError");
        show(err.id);
        return;
      }
      currentBackupRows = res.body.rows;
      renderBackupTable();
      hide("backup-step-input");
      show("backup-step-preview");
    });
  });

  $("backup-table-body").addEventListener("change", function (e) {
    var field = e.target.dataset.field;
    if (!field) return;
    var idx = Number.parseInt(e.target.dataset.index, 10);
    currentBackupRows[idx][field] = e.target.value;
    if (field === "box" && e.target.value) {
      currentBackupRows[idx].action = "import";
    }
  });

  $("backup-commit-btn").addEventListener("click", function () {
    var rowsToCommit = currentBackupRows.map(function (row) { return Object.assign({}, row); });
    $("backup-commit-btn").disabled = true;
    api("api/backup/import/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows: rowsToCommit }),
    }).then(function (res) {
      $("backup-commit-btn").disabled = false;
      var result = $("backup-result");
      if (!res.ok) {
        result.className = "banner error";
        result.textContent = res.body.text || t("backup.commitError");
        show(result.id);
        return;
      }
      var body = res.body;
      result.className = body.errors.length ? "banner warn" : "banner ok";
      result.textContent =
        t("backup.resultSummary", { imported: body.imported, overwritten: body.overwritten, skipped: body.skipped }) +
        (body.errors.length ? t("backup.resultErrors", { errors: body.errors.join(" | ") }) : "");
      show(result.id);
    });
  });

})();
