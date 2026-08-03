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
  var backToHome           = ns.backToHome;
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

    var band433 = channels.filter(function (c) { return c.band === 1 && c.getDecoder !== 0; });
    var band868 = channels.filter(function (c) { return c.band === 2 && c.getDecoder !== 0; });

    var BAND_LABELS = { 1: "433 MHz", 2: "868 MHz" };
    [[1, band433], [2, band868]].forEach(function (pair) {
      var band = pair[0];
      var list = pair[1];
      if (!list.length) { return; }
      var grp = document.createElement("optgroup");
      grp.label = BAND_LABELS[band];
      list.forEach(function (c) {
        var opt = document.createElement("option");
        opt.value = String(c.id);
        opt.textContent = c.name;
        grp.appendChild(opt);
      });
      sel.appendChild(grp);
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

  function buildInboxRow(c) {
    var row = document.createElement("div");
    row.className = "candidate";

    var info = document.createElement("span");
    var protocolLabel = c.protocol_name || (c.decoded
      ? t("wizard.listen.channelFallback", { id: c.channel_id })
      : t("inbox.undecoded"));
    info.innerHTML =
      "<strong>" + protocolLabel + "</strong> · " + inboxBandLabel(c.band) +
      "<br><span class='muted'>" +
        t("inbox.seenCount", { n: c.seen_count }) + " · " +
        t("inbox.lastSeen", { when: formatCandidateTime(c.last_seen) }) +
      "</span>";

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
  $("inbox-capture-unknown-checkbox").addEventListener("change", function () {
    var checkbox = this;
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
        syncChannelSelect(res.body && res.body.bind_channel_id);
      }
    });
  });

  $("btn-open-inbox").addEventListener("click", function () {
    inboxState.selected = null;
    hide("inbox-confirm-form");
    hide("screen-home");
    show("screen-inbox");
    loadInboxSettings();
    loadInboxCandidates();
  });

  $("btn-inbox-cancel").addEventListener("click", backToHome);

})();
