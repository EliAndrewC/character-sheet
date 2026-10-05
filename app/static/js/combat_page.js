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
      drag: null,
      lineMenu: null,

      start: function () {
        var self = this;
        this._timer = setInterval(function () { self.poll(); }, POLL_MS);
        // A tab coming back into view catches up at once, not a tick later.
        document.addEventListener("visibilitychange", function () {
          if (!document.hidden) self.poll();
        });
        // Striking lines follow every redraw, resize and card-height change.
        this.$watch("state", function () { self.$nextTick(function () { self.drawReach(); }); });
        window.addEventListener("resize", function () { self.drawReach(); });
        if (window.ResizeObserver && this.$refs.arena) {
          new ResizeObserver(function () { self.drawReach(); }).observe(this.$refs.arena);
        }
        this.$nextTick(function () { self.drawReach(); });
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
        if (this.busy || this.drag || (document.hidden && !this.playerView)) return;
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
      // A player's view of an NPC's dice: the spent ones (public, with
      // their values), then a "?" for each action known from earlier rounds.
      publicDice: function (npc) {
        var out = (npc.spent_dice || []).map(function (v) { return { value: v, spent: true }; });
        for (var i = 0; i < (npc.unknown_dice || 0); i++) out.push({ value: "?", spent: false });
        return out;
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

      // ---- striking distance: undirected PC <-> NPC lines ----
      // The pairs to draw: the GM's while their switch is on; players only
      // ever receive them while it is on.
      reachPairs: function () {
        if (this.gm && !this.state.show_reach) return [];
        return this.state.reach || [];
      },
      reachShown: function () { return this.reachPairs().length > 0; },
      hasReach: function (pc, npc) {
        return (this.state.reach || []).some(function (p) { return p[0] === pc && p[1] === npc; });
      },
      reachNames: function (side, id) {
        var mine = side === "pcs" ? 0 : 1;
        var others = side === "pcs" ? this.state.npcs : this.state.pcs;
        var ids = this.reachPairs().filter(function (p) { return p[mine] === id; })
          .map(function (p) { return p[1 - mine]; });
        return others.filter(function (o) { return ids.indexOf(o.id) >= 0; })
          .map(function (o) { return o.name; });
      },
      toggleReach: async function (pc, npc, on) {
        await this.post("/reach", { pc_id: pc, npc_id: npc, on: on });
      },
      setShowReach: async function (visible) {
        this.closeLineMenu();
        await this.post("/reach-visible", { visible: visible });
      },
      closeLineMenu: function () {
        if (!this.lineMenu) return;
        this.lineMenu = null;
        this.drawReach();
      },
      removeLine: async function () {
        var m = this.lineMenu;
        this.lineMenu = null;
        if (m) await this.toggleReach(m.pc, m.npc, false);
      },
      // Draw each pair as a curve from the PC card's right edge to the NPC
      // card's left edge, across the strip between the columns. A card's
      // lines fan out along its edge in the order of the cards they reach,
      // so they do not meet in one point or cross needlessly.
      drawReach: function () {
        var svg = this.$refs.reachSvg, arena = this.$refs.arena;
        if (!svg || !arena) return;
        while (svg.firstChild) svg.removeChild(svg.firstChild);
        var pairs = this.reachPairs();
        if (!pairs.length || window.innerWidth < 1024) return;
        var self = this, NS = "http://www.w3.org/2000/svg";
        var box = arena.getBoundingClientRect();
        var card = function (side, id) {
          return arena.querySelector('[data-testid="' + side + '-card-' + id + '"]');
        };
        var rect = {};
        pairs.forEach(function (p) {
          [["pc", p[0]], ["npc", p[1]]].forEach(function (k) {
            var key = k[0] + k[1];
            if (!(key in rect)) { var el = card(k[0], k[1]); rect[key] = el ? el.getBoundingClientRect() : null; }
          });
        });
        var mid = function (r) { return r.top + r.height / 2; };
        var anchor = function (side, id, otherSide, otherId) {
          var mine = pairs.filter(function (p) { return p[side === "pc" ? 0 : 1] === id; })
            .map(function (p) { return p[side === "pc" ? 1 : 0]; })
            .filter(function (o) { return rect[otherSide + o]; })
            .sort(function (a, b) { return mid(rect[otherSide + a]) - mid(rect[otherSide + b]); });
          var r = rect[side + id], i = mine.indexOf(otherId);
          return r.top + r.height * (0.2 + 0.6 * (i + 1) / (mine.length + 1)) - box.top;
        };
        pairs.forEach(function (p) {
          var a = rect["pc" + p[0]], b = rect["npc" + p[1]];
          if (!a || !b) return;
          var x1 = a.right - box.left, x2 = b.left - box.left;
          var y1 = anchor("pc", p[0], "npc", p[1]), y2 = anchor("npc", p[1], "pc", p[0]);
          var mx = (x1 + x2) / 2;
          var d = "M " + x1 + " " + y1 + " C " + mx + " " + y1 + ", " + mx + " " + y2 + ", " + x2 + " " + y2;
          var on = self.lineMenu && self.lineMenu.pc === p[0] && self.lineMenu.npc === p[1];
          var line = document.createElementNS(NS, "path");
          line.setAttribute("d", d);
          line.setAttribute("fill", "none");
          // Theme colours go in style: SVG attributes do not resolve var().
          line.style.stroke = on ? "rgb(var(--color-accent))" : "rgb(var(--color-ink) / 0.45)";
          line.setAttribute("stroke-width", on ? "3.5" : "2");
          line.setAttribute("stroke-linecap", "round");
          line.setAttribute("data-testid", "reach-line-" + p[0] + "-" + p[1]);
          svg.appendChild(line);
          [[x1, y1], [x2, y2]].forEach(function (pt) {
            var dot = document.createElementNS(NS, "circle");
            dot.setAttribute("cx", pt[0]); dot.setAttribute("cy", pt[1]); dot.setAttribute("r", on ? "4" : "3");
            dot.style.fill = on ? "rgb(var(--color-accent))" : "rgb(var(--color-ink) / 0.45)";
            svg.appendChild(dot);
          });
          if (!self.gm) return;
          // The GM clicks a line (on a wide invisible stroke) to remove it.
          var hit = document.createElementNS(NS, "path");
          hit.setAttribute("d", d);
          hit.setAttribute("fill", "none");
          hit.setAttribute("stroke", "transparent");
          hit.setAttribute("stroke-width", "14");
          hit.setAttribute("data-testid", "reach-hit-" + p[0] + "-" + p[1]);
          hit.style.pointerEvents = "stroke";
          hit.style.cursor = "pointer";
          hit.addEventListener("click", function (e) {
            e.stopPropagation();
            var pc = self.state.pcs.find(function (c) { return c.id === p[0]; });
            var npc = self.state.npcs.find(function (c) { return c.id === p[1]; });
            self.lineMenu = { pc: p[0], npc: p[1], x: e.clientX - box.left, y: e.clientY - box.top,
                              label: (pc ? pc.name : "?") + " \u2194 " + (npc ? npc.name : "?") };
            self.drawReach();
          });
          svg.appendChild(hit);
        });
      },

      // ---- standing order: the GM drags a card by its grip ----
      // Pointer events (mouse and touch alike). Each side reorders only
      // within its own column: the move compares the pointer with the cards
      // of the side being dragged, so a PC can never land among the NPCs.
      startDrag: function (event, side, id) {
        if (!this.gm) return;
        event.preventDefault();
        var self = this;
        this.drag = { side: side, id: id };
        var move = function (e) { self.dragTo(e.clientY); };
        var up = function () {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
          window.removeEventListener("pointercancel", up);
          self.endDrag();
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
        window.addEventListener("pointercancel", up);
      },
      dragTo: function (y) {
        var d = this.drag;
        if (!d) return;
        var list = this.state[d.side];
        var from = list.findIndex(function (c) { return c.id === d.id; });
        // The new place is how many OTHER cards on this side sit above the pointer.
        var cards = document.querySelectorAll('[data-order-side="' + d.side + '"] [data-order-id]');
        var to = 0;
        cards.forEach(function (el, i) {
          if (i === from) return;
          var r = el.getBoundingClientRect();
          if (y > r.top + r.height / 2) to++;
        });
        if (to === from || from < 0) return;
        var moved = list.splice(from, 1)[0];
        list.splice(to, 0, moved);
        d.moved = true;
        var self = this;
        this.$nextTick(function () { self.drawReach(); });
      },
      endDrag: async function () {
        var d = this.drag;
        this.drag = null;
        if (!d || !d.moved) return;
        var ids = this.state[d.side].map(function (c) { return c.id; });
        var data = await this.post("/order", { side: d.side, ids: ids });
        if (data === null) await this.refresh();
      },

      // ---- the NPC roll overlay ----
      // A character's dice, light wounds, initiative and rolls use the
      // sheet's OWN die menu, light-wounds modal, roll menu and roll modals
      // (one implementation): served for that character by /roller/{id} and
      // laid over this page in a full-window, transparent iframe. ``die``
      // opens that die's menu just under the clicked die; mode "initiative"
      // the initiative menu there; otherwise the light-wounds modal (its
      // wound check is the sheet's). The GM may open any NPC or PC; a
      // player only a PC they can edit. The overlay says when nothing is
      // open any more; then it goes and the state refreshes.
      openRoller: function (who, die, event, mode) {
        this.closeRoller();
        var r = event.currentTarget.getBoundingClientRect();
        var at = "&x=" + Math.round(r.left + r.width / 2) + "&y=" + Math.round(r.bottom);
        var query = mode === "initiative" ? "?initiative=1" + at
          : die !== null ? "?die=" + die + at : "?wounds=1";
        var frame = document.createElement("iframe");
        frame.src = this.url("/roller/" + who.id) + query;
        frame.title = who.name;
        frame.setAttribute("data-testid", "npc-roller-frame");
        frame.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;border:0;" +
          "z-index:60;background:transparent;color-scheme:normal";
        frame.allowTransparency = true;
        document.body.appendChild(frame);
        this._roller = { frame: frame, id: who.id };
      },
      closeRoller: function () {
        if (this._roller) this._roller.frame.remove();
        this._roller = null;
      },
      onRollerClosed: async function () {
        var npcId = this._roller && this._roller.id;
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
