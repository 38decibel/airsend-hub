// screen-inbox.js — Inbox (captured RF signals) screen logic
// Depends on window.AirSend (populated by the main inline script before this file runs)
(function () {
  "use strict";

  var ns = window.AirSend;
  var t                    = ns.t;
  var api                  = ns.api;
  var $                    = ns.$;
  var show                 = ns.show;
  var hide                 = ns.hide;
  var state                = ns.state;         // used for currentLang proxy
  var populateCategorySelect = ns.populateCategorySelect;

  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------
  var inboxState = { selected: null, kind: null };

  // -----------------------------------------------------------------------
  // Helpers
  // -----------------------------------------------------------------------
  function formatCandidateTime(epochSeconds) {
    try {
      return new Date(epochSeconds * 1000).toLocaleTimeString(
        window.currentLang === "en" ? "en-US" : "fr-FR"
      );
    } catch (e) {
      return "";
    }
  }

  function inboxBandLabel(band) {
    if (band === 2) return t("inbox.band868");
    if (band === 1) return t("inbox.band433");
    return t("inbox.bandUnknown");
  }

  function syncCaptureUnknownCheckbox(enabled) {
    $("inbox-capture-unknown-checkbox").checked = !!enabled;
  }

  function syncChannelSelect(channelId) {
    var sel = $("inbox-channel-select");
    sel.value = (channelId === null || channelId === undefined) ? "" : String(channelId);
  }

  function populateChannelSelect(channels, currentChannelId) {
    var sel = $("inbox-channel-select");
    // Keep the first default option only
    while (sel.options.length > 1) { sel.remove(1); }

    var BAND_LABELS = { 1: "433", 2: "868" };
    // Sort by band then name; skip send-only protocols (getDecoder === 0)
    var sorted = channels
      .filter(function (c) { return c.getDecoder !== 0; })
      .sort(function (a, b) {
        if (a.band !== b.band) { return a.band - b.band; }
        return a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
      });

    sorted.forEach(function (c) {
      var opt = document.createElement("option");
      opt.value = String(c.id);
      opt.textContent = "[" + (BAND_LABELS[c.band] || c.band) + "] " + c.name;
      sel.appendChild(opt);
    });

    syncChannelSelect(currentChannelId);
  }

  function loadInboxSettings() {
    api("api/settings").then(function (res) {
      if (!res.ok) { return; }
      syncCaptureUnknownCheckbox(res.body.capture_unknown_events);
      var currentChannelId = res.body.bind_channel_id;
      api("api/channels").then(function (chRes) {
        if (chRes.ok && Array.isArray(chRes.body)) {
          populateChannelSelect(chRes.body, currentChannelId);
        } else {
          syncChannelSelect(currentChannelId);
        }
      });
    });
  }

  function updateInboxConfirmEnabled() {
    $("btn-inbox-confirm").disabled = !(inboxState.kind && $("inbox-name-input").value.trim());
  }

  function openInboxConfirm(c) {
    inboxState.selected = c;
    inboxState.kind     = null;
    $("inbox-name-input").value = "";
    populateCategorySelect($("inbox-category-select"));
    document.querySelectorAll("#inbox-kind-choices .choice-box").forEach(function (b) { b.classList.remove("selected"); });
    hide("inbox-confirm-banner");
    updateInboxConfirmEnabled();
    show("inbox-confirm-form");
    $("inbox-confirm-form").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function forgetInboxCandidate(c) {
    if (!window.confirm(t("inbox.forgetConfirm", { channelId: c.channel_id, channelSource: c.channel_source }))) {
      return;
    }
    api("api/inbox/forget", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ box: c.box, channel_id: c.channel_id, channel_source: c.channel_source }),
    }).then(function () { loadInboxCandidates(); });
  }

  function formatNotes(notes) {
    if (!Array.isArray(notes) || !notes.length) { return "—"; }
    var TYPE_LABELS = { 0: "STATE", 1: "DATA", 2: "TEMP", 3: "LUX", 4: "HUM", 9: "LEVEL" };
    var METHOD_LABELS = { 0: "QUERY", 1: "PUT", 2: "INFO" };
    return notes.map(function (n) {
      var m = METHOD_LABELS[n.method] || n.method;
      var ty = TYPE_LABELS[n.type] || n.type;
      return m + " " + ty + (n.value !== undefined ? "=" + n.value : "");
    }).join(" · ");
  }

  function buildInboxRow(c) {
    var row = document.createElement("div");
    row.className = "candidate";

    var protocolLabel;
    if (c.protocol_name) {
      protocolLabel = c.protocol_name;
    } else if (c.decoded) {
      protocolLabel = t("wizard.listen.channelFallback", { id: c.channel_id });
    } else {
      protocolLabel = t("inbox.undecoded");
    }

    // ── Summary line (always visible) ──
    var summary = document.createElement("div");
    summary.className = "candidate-summary";
    summary.innerHTML =
      "<strong>" + protocolLabel + "</strong> · " + inboxBandLabel(c.band) +
      "<br><span class='muted'>" +
        t("inbox.seenCount", { n: c.seen_count }) + " · " +
        t("inbox.lastSeen", { when: formatCandidateTime(c.last_seen) }) +
        (c.last_action ? " · <strong>" + c.last_action + "</strong>" : "") +
      "</span>";

    // ── Detail block (collapsed by default) ──
    var detail = document.createElement("div");
    detail.className = "candidate-detail hidden";
    detail.innerHTML =
      "<span class='muted'>" + t("inbox.detailChannelId") + "</span> " + c.channel_id +
      "<br><span class='muted'>" + t("inbox.detailSource") + "</span> " + c.channel_source +
      "<br><span class='muted'>" + t("inbox.detailFirstSeen") + "</span> " + formatCandidateTime(c.first_seen) +
      "<br><span class='muted'>" + t("inbox.detailLastNotes") + "</span> " + formatNotes(c.last_notes);

    // Toggle detail on summary click
    summary.style.cursor = "pointer";
    var expanded = false;
    summary.addEventListener("click", function () {
      expanded = !expanded;
      if (expanded) { detail.classList.remove("hidden"); } else { detail.classList.add("hidden"); }
    });

    var actions = document.createElement("span");
    actions.className = "device-actions";

    var includeBtn = document.createElement("button");
    includeBtn.className   = "icon-btn";
    includeBtn.textContent = t("inbox.include");
    includeBtn.addEventListener("click", function () { openInboxConfirm(c); });

    var forgetBtn = document.createElement("button");
    forgetBtn.className   = "icon-btn danger";
    forgetBtn.textContent = t("inbox.forget");
    forgetBtn.addEventListener("click", function () { forgetInboxCandidate(c); });

    actions.appendChild(includeBtn);
    actions.appendChild(forgetBtn);

    var info = document.createElement("span");
    info.appendChild(summary);
    info.appendChild(detail);

    row.appendChild(info);
    row.appendChild(actions);
    return row;
  }

  function loadInboxCandidates() {
    var list = $("inbox-list");
    list.innerHTML = "";
    api("api/inbox").then(function (res) {
      if (!res.ok) {
        hide("inbox-empty");
        list.textContent = t("inbox.loadError");
        return;
      }
      syncCaptureUnknownCheckbox(res.body.capture_unknown_events);
      var candidates = res.body.candidates || [];
      if (!candidates.length) {
        show("inbox-empty");
        return;
      }
      hide("inbox-empty");
      candidates.forEach(function (c) { list.appendChild(buildInboxRow(c)); });
    });
  }

  // -----------------------------------------------------------------------
  // Event listeners
  // -----------------------------------------------------------------------
  $("inbox-capture-unknown-checkbox").addEventListener("change", function (e) {
    var checkbox = e.currentTarget;
    var desired  = checkbox.checked;
    api("api/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ capture_unknown_events: desired }),
    }).then(function (res) {
      if (!res.ok) {
        checkbox.checked = !desired;
        window.alert(t("inbox.settingsError"));
      }
    });
  });

  $("btn-inbox-confirm-cancel").addEventListener("click", function () {
    inboxState.selected = null;
    hide("inbox-confirm-form");
  });

  document.querySelectorAll("#inbox-kind-choices .choice-box").forEach(function (box) {
    box.addEventListener("click", function () {
      document.querySelectorAll("#inbox-kind-choices .choice-box").forEach(function (b) { b.classList.remove("selected"); });
      box.classList.add("selected");
      inboxState.kind = box.dataset.kind;
      updateInboxConfirmEnabled();
    });
  });

  $("inbox-name-input").addEventListener("input", updateInboxConfirmEnabled);

  $("btn-inbox-confirm").addEventListener("click", function () {
    var c = inboxState.selected;
    if (!c) return;
    var options = {};
    var chosenCategory = $("inbox-category-select").value;
    if (chosenCategory) { options.display_category = chosenCategory; }

    var banner = $("inbox-confirm-banner");
    hide(banner.id);
    $("btn-inbox-confirm").disabled = true;
    api("api/inbox/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        box:           c.box,
        channel_id:    c.channel_id,
        channel_source: c.channel_source,
        kind:          inboxState.kind,
        friendly_name: $("inbox-name-input").value.trim(),
        options:       options,
      }),
    }).then(function (res) {
      if (!res.ok) {
        banner.className   = "banner error";
        banner.textContent = res.body.text || t("wizard.kind.creationError");
        show(banner.id);
        $("btn-inbox-confirm").disabled = false;
        return;
      }
      inboxState.selected = null;
      hide("inbox-confirm-form");
      loadInboxCandidates();
    });
  });

  $("inbox-channel-select").addEventListener("change", function () {
    var sel = $("inbox-channel-select");
    var raw = sel.value;
    var channelId = raw === "" ? null : Number.parseInt(raw, 10);
    api("api/settings", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bind_channel_id: channelId }),
    }).then(function (res) {
      if (!res.ok) {
        window.alert(t("inbox.settingsError"));
        syncChannelSelect(res.body?.bind_channel_id);
      }
    });
  });

  window.AirSend.openInbox = function () {
    inboxState.selected = null;
    hide("inbox-confirm-form");
    loadInboxSettings();
    loadInboxCandidates();
  };

})();
