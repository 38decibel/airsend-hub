// screen-memory.js — Box memory screen logic
// Depends on window.AirSend (populated by the main inline script before this file runs)
(function () {
  "use strict";

  var ns                   = window.AirSend;
  var t                    = ns.t;
  var api                  = ns.api;
  var $                    = ns.$;
  var show                 = ns.show;
  var hide                 = ns.hide;
  var backToHome           = ns.backToHome;
  var populateCategorySelect = ns.populateCategorySelect;

  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------
  var memoryState = { selected: null, kind: null };

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------
  function updateAddConfirmEnabled() {
    $("btn-memory-add-confirm").disabled = !(
      memoryState.kind && $("memory-name-input").value.trim()
    );
  }

  function openAddForm(entry) {
    memoryState.selected = entry;
    memoryState.kind     = null;
    $("memory-name-input").value = "";
    populateCategorySelect($("memory-category-select"));
    document.querySelectorAll("#memory-kind-choices .choice-box").forEach(function (b) {
      b.classList.remove("selected");
    });
    hide("memory-add-banner");
    updateAddConfirmEnabled();
    show("memory-add-form");
    $("memory-add-form").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function closeAddForm() {
    memoryState.selected = null;
    memoryState.kind     = null;
    hide("memory-add-form");
  }

  function buildMemoryRow(entry) {
    var row = document.createElement("div");
    row.className = "candidate";

    var isLinked = !!(entry.device_key);
    var statusLabel = isLinked ? t("memory.linked") : t("memory.orphan");
    var statusClass = isLinked ? "tag-linked" : "tag-orphan";

    var info = document.createElement("span");
    info.innerHTML =
      "<strong>" + (entry.protocol_name || "id=" + entry.channel_id) + "</strong>" +
      " · <span class='" + statusClass + "'>" + statusLabel + "</span>" +
      (isLinked ? " → <em>" + entry.device_name + "</em>" : "") +
      "<br><span class='muted'>source=" + entry.source +
      " · " + t("memory.counter", { n: entry.counter }) + "</span>";

    var actions = document.createElement("span");
    actions.className = "device-actions";

    if (!isLinked) {
      var addBtn = document.createElement("button");
      addBtn.className   = "icon-btn";
      addBtn.textContent = t("memory.add");
      addBtn.addEventListener("click", function () { openAddForm(entry); });
      actions.appendChild(addBtn);
    }

    row.appendChild(info);
    row.appendChild(actions);
    return row;
  }

  function loadMemory() {
    var list = $("memory-list");
    list.innerHTML = "";
    hide("memory-error");
    show("memory-loading");

    api("api/memory").then(function (res) {
      hide("memory-loading");
      if (!res.ok) {
        $("memory-error").textContent = t("memory.loadError");
        show("memory-error");
        return;
      }
      var entries = res.body;
      var badge = $("memory-usage-badge");
      if (!Array.isArray(entries) || !entries.length) {
        list.textContent = t("home.noDevices");
        hide("memory-usage-badge");
        return;
      }
      badge.textContent = t("memory.usage", { n: entries.length, max: 45 });
      show("memory-usage-badge");
      entries.forEach(function (entry) { list.appendChild(buildMemoryRow(entry)); });
    });
  }

  // -----------------------------------------------------------------------
  // Event listeners
  // -----------------------------------------------------------------------
  document.querySelectorAll("#memory-kind-choices .choice-box").forEach(function (box) {
    box.addEventListener("click", function () {
      document.querySelectorAll("#memory-kind-choices .choice-box").forEach(function (b) {
        b.classList.remove("selected");
      });
      box.classList.add("selected");
      memoryState.kind = box.dataset.kind;
      updateAddConfirmEnabled();
    });
  });

  $("memory-name-input").addEventListener("input", updateAddConfirmEnabled);

  $("btn-memory-add-cancel").addEventListener("click", closeAddForm);

  $("btn-memory-add-confirm").addEventListener("click", function () {
    var entry = memoryState.selected;
    if (!entry) return;

    var options = {};
    var chosenCategory = $("memory-category-select").value;
    if (chosenCategory) { options.display_category = chosenCategory; }

    var banner = $("memory-add-banner");
    hide(banner.id);
    $("btn-memory-add-confirm").disabled = true;

    api("api/devices/manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        box:            entry.box || null,
        channel_id:     entry.channel_id,
        channel_source: entry.source,
        kind:           memoryState.kind,
        friendly_name:  $("memory-name-input").value.trim(),
        options:        options,
      }),
    }).then(function (res) {
      if (!res.ok) {
        banner.className   = "banner error";
        banner.textContent = (res.body && res.body.message) || t("memory.creationError");
        show(banner.id);
        $("btn-memory-add-confirm").disabled = false;
        return;
      }
      closeAddForm();
      loadMemory();
    });
  });

  $("btn-open-memory").addEventListener("click", function () {
    closeAddForm();
    hide("screen-home");
    show("screen-memory");
    loadMemory();
  });

  $("btn-memory-cancel").addEventListener("click", backToHome);

})();
