// The combat page's Alpine component (app/templates/group_combat.html,
// combat-design/design.md 4.5). Every NPC action is resolved on the server
// (app/routes/combat.py); this file only collects the GM's choices, posts
// them, and shows the result. The page polls its state every few seconds
// and redraws only when the server's `rev` moved.
(function () {
  "use strict";

  var POLL_MS = 4000;

  function pct(share) {
    return share == null ? "?" : Math.round(share * 100);
  }

  function newRow(share) {
    return {
      npc_type: "wave_man", count: 1, earned_xp: 50, roll_extra: true,
      combat_target: share.default, exact_share: false,
    };
  }

  // playerView: the GM's "Player view" tab (?view=player), shown as players
  // see it for screen sharing. It polls the public state, and keeps polling
  // while hidden: a shared window can count as hidden when it is covered.
  window.combatPage = function (groupId, gm, state, npcTypes, share, playerView) {
    return {
      groupId: groupId,
      gm: gm,
      playerView: !!playerView,
      state: state,
      npcTypes: npcTypes,
      share: share,
      busy: false,
      error: "",
      fightName: "",
      rows: [newRow(share)],
      roster: null,
      dlg: null,
      _timer: null,
      _roller: null,

      start: function () {
        var self = this;
        this._timer = setInterval(function () { self.poll(); }, POLL_MS);
        // A tab coming back into view catches up at once, not a tick later.
        document.addEventListener("visibilitychange", function () {
          if (!document.hidden) self.poll();
        });
        window.addEventListener("message", function (e) {
          if (e.origin === window.location.origin && e.data && e.data.type === "l7r-npc-roller-closed") {
            self.onRollerClosed();
          }
        });
      },

      stateUrl: function () {
        return this.url("/state") + (this.playerView ? "?view=player" : "");
      },

      url: function (path) {
        return "/groups/" + this.groupId + "/combat" + (path || "");
      },

      poll: async function () {
        if (this.busy || (document.hidden && !this.playerView)) return;
        try {
          var resp = await fetch(this.stateUrl(), { cache: "no-store" });
          if (!resp.ok) return;
          var data = await resp.json();
          if (data.rev !== this.state.rev) this.state = data;
        } catch (e) { /* the next tick tries again */ }
      },

      refresh: async function () {
        var resp = await fetch(this.stateUrl(), { cache: "no-store" });
        if (resp.ok) this.state = await resp.json();
      },

      // POST, then refresh the state. Returns the JSON body, or null on an
      // error (shown in the dialog if one is open, else on the page).
      post: async function (path, body) {
        this.busy = true;
        this.error = "";
        if (this.dlg) this.dlg.error = "";
        try {
          var resp = await fetch(this.url(path), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body || {}),
          });
          var data = await resp.json().catch(function () { return {}; });
          if (!resp.ok) {
            var msg = data.message || data.error || ("Request failed (" + resp.status + ")");
            if (this.dlg) this.dlg.error = msg; else this.error = msg;
            return null;
          }
          await this.refresh();
          return data;
        } finally {
          this.busy = false;
        }
      },

      // ---- helpers for the template ----
      pct: pct,
      voidText: function (c) {
        var extra = [];
        if (c.temp_void) extra.push("+" + c.temp_void + " temp");
        if (c.worldliness_void) extra.push("+" + c.worldliness_void + " worldliness");
        return c.void + "/" + c.void_max + (extra.length ? " (" + extra.join(", ") + ")" : "");
      },
      bonusText: function (b) {
        if (b.left !== undefined) return b.name + ": " + b.left + "/" + b.max;
        return b.name + (b.used ? ": used" : ": ready");
      },
      publicActionText: function (a) {
        var s = a.label;
        if (a.target) s += " on " + a.target;
        if (a.total !== null && a.total !== undefined) s += ": " + a.total;
        if (a.outcome === "missed") s += ", missed";
        else if (a.outcome === "parried") s += ", parried";
        else if (a.outcome === "failed") s += ", failed";
        if (a.damage !== null && a.damage !== undefined) s += ", " + a.damage + " damage";
        return s;
      },
      gmActionText: function (a) {
        var d = a.detail || {};
        var s = "R" + a.round + " " + a.npc + ": " + a.label;
        if (a.target) s += " on " + a.target;
        if (a.total !== null && a.total !== undefined) s += " " + a.total;
        if (d.effective_tn !== undefined) s += " vs " + d.effective_tn;
        if (d.outcome) s += " (" + d.outcome + ")";
        if (d.damage !== undefined) s += ", " + d.damage + " damage";
        if (d.void) s += ", " + d.void + " void";
        return s;
      },

      // ---- fight ----
      startFight: async function (replace) {
        var data = await this.post("/start", { name: this.fightName, replace: replace });
        if (data === null && /still going/.test(this.error)) {
          if (window.confirm(this.error)) {
            this.error = "";
            await this.startFight(true);
          }
        }
      },
      endFight: async function () {
        if (!window.confirm("End this fight? Its NPCs stay in the roster.")) return;
        await this.post("/end");
        if (this.roster !== null) await this.loadRoster();
      },
      newRound: async function () { await this.post("/new-round"); },
      rollInitiative: async function (npc) { await this.post("/npcs/" + npc.id + "/initiative"); },

      // ---- builder ----
      addRow: function () { this.rows.push(newRow(this.share)); },
      generate: async function () {
        var rows = this.rows.map(function (r) {
          var row = {
            npc_type: r.npc_type, count: r.count, earned_xp: r.earned_xp,
            roll_extra: !!r.roll_extra, combat_target: r.combat_target,
          };
          if (r.exact_share) row.combat_share = r.combat_target;
          return row;
        });
        var data = await this.post("/generate", { rows: rows });
        if (data !== null) {
          this.rows = [newRow(this.share)];
          if (this.roster !== null) await this.loadRoster();
        }
      },

      // ---- roster ----
      loadRoster: async function () {
        var resp = await fetch(this.url("/roster"), { cache: "no-store" });
        if (!resp.ok) return;
        var data = await resp.json();
        this.roster = data.npcs.map(function (r) { r.gained = 0; return r; });
      },
      bringBack: async function (r) {
        var data = await this.post("/roster/" + r.id + "/bring-back", { gained_xp: r.gained || 0 });
        if (data !== null) await this.loadRoster();
      },
      deleteNpc: async function (r) {
        if (!window.confirm("Delete " + r.name + " for good?")) return;
        var data = await this.post("/roster/" + r.id + "/delete");
        if (data !== null) await this.loadRoster();
      },

      // ---- NPC card controls ----
      setStatus: async function (npc, status, closeAfter) {
        var data = await this.post("/npcs/" + npc.id + "/status", { status: status });
        if (data !== null && closeAfter) this.closeDialog();
      },
      removeNpc: async function (npc) {
        if (!window.confirm(npc.name + " leaves this fight (they stay in the roster)?")) return;
        await this.post("/npcs/" + npc.id + "/remove");
      },

      // ---- the NPC roll overlay ----
      // An NPC's dice, light wounds and rolls use the sheet's OWN die menu,
      // light-wounds modal and roll modals (one implementation): they are
      // served for that NPC by /npcs/{id}/roller and laid over this page in
      // a full-window, transparent iframe. ``die`` opens that die's menu
      // just under the clicked die; null opens the light-wounds modal (its
      // wound check is the sheet's). The overlay says when nothing is open
      // any more; then it goes and the state refreshes.
      openRoller: function (npc, die, event) {
        this.closeRoller();
        var query = "?wounds=1";
        if (die !== null) {
          var r = event.currentTarget.getBoundingClientRect();
          query = "?die=" + die + "&x=" + Math.round(r.left + r.width / 2) + "&y=" + Math.round(r.bottom);
        }
        var frame = document.createElement("iframe");
        frame.src = this.url("/npcs/" + npc.id + "/roller") + query;
        frame.title = npc.name;
        frame.setAttribute("data-testid", "npc-roller-frame");
        frame.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;border:0;" +
          "z-index:60;background:transparent;color-scheme:normal";
        frame.allowTransparency = true;
        document.body.appendChild(frame);
        this._roller = { frame: frame, npc: npc.id };
      },
      closeRoller: function () {
        if (this._roller) this._roller.frame.remove();
        this._roller = null;
      },
      onRollerClosed: async function () {
        var npcId = this._roller && this._roller.npc;
        this.closeRoller();
        await this.refresh();
        // At 2 x Earth serious wounds the GM says unconscious or dead (D9).
        var npc = (this.state.npcs || []).find(function (n) { return n.id === npcId; });
        if (npc && npc.status === "fighting" && npc.serious_wounds >= npc.max_serious_wounds) {
          this.promptDown(npc);
        }
      },

      // ---- dialogs ----
      openDialog: function (kind, npc) {
        var d = { kind: kind, npc: npc, error: "" };
        if (kind === "adjust") {
          d.light = npc.light_wounds; d.serious = npc.serious_wounds; d.voidPts = npc.void;
        }
        if (kind === "rebuild") { d.earned = npc.earned_xp; d.share = pct(npc.combat_share); }
        if (kind === "rename") d.name = npc.name;
        this.dlg = d;
      },
      closeDialog: function () { this.dlg = null; },
      dialogTitle: function () {
        if (!this.dlg) return "";
        var titles = {
          down: this.dlg.npc.name + " is down",
          adjust: "Adjust " + this.dlg.npc.name,
          rebuild: "Rebuild " + this.dlg.npc.name,
          rename: "Rename " + this.dlg.npc.name,
        };
        return titles[this.dlg.kind] || "";
      },

      promptDown: function (npc) {
        this.dlg = { kind: "down", npc: npc, error: "" };
      },
      saveAdjust: async function () {
        var d = this.dlg;
        var data = await this.post("/npcs/" + d.npc.id + "/tracking",
                                   { light: d.light, serious: d.serious, void: d.voidPts });
        if (data === null) return;
        if (data.down_prompt) this.promptDown(d.npc); else this.closeDialog();
      },
      saveRebuild: async function () {
        var d = this.dlg;
        var data = await this.post("/npcs/" + d.npc.id + "/rebuild",
                                   { earned_xp: d.earned, combat_share: d.share });
        if (data !== null) this.closeDialog();
      },
      saveRename: async function () {
        var d = this.dlg;
        var data = await this.post("/npcs/" + d.npc.id + "/rename", { name: d.name });
        if (data !== null) this.closeDialog();
      },
    };
  };
})();
