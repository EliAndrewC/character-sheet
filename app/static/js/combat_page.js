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
  window.combatPage = function (groupId, gm, state, npcTypes, share, weapons, playerView) {
    return {
      groupId: groupId,
      gm: gm,
      playerView: !!playerView,
      state: state,
      npcTypes: npcTypes,
      share: share,
      weapons: weapons,
      busy: false,
      error: "",
      fightName: "",
      rows: [newRow(share)],
      roster: null,
      dlg: null,
      _timer: null,

      start: function () {
        var self = this;
        this._timer = setInterval(function () { self.poll(); }, POLL_MS);
        // A tab coming back into view catches up at once, not a tick later.
        document.addEventListener("visibilitychange", function () {
          if (!document.hidden) self.poll();
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

      // ---- dialogs ----
      openMenu: function (npc, die) {
        this.dlg = { kind: "menu", npc: npc, die: die, error: "", step: null, result: null,
                     void: 0, label: "", attackTotal: null, attacker: "", predeclared: false,
                     interrupt: false, secondDie: null };
      },
      openDialog: function (kind, npc) {
        var d = { kind: kind, npc: npc, error: "", result: null, void: 0, chosen: false };
        if (kind === "damage") d.amount = null;
        if (kind === "adjust") {
          d.light = npc.light_wounds; d.serious = npc.serious_wounds; d.voidPts = npc.void;
        }
        if (kind === "rebuild") { d.earned = npc.earned_xp; d.share = pct(npc.combat_share); }
        if (kind === "rename") d.name = npc.name;
        this.dlg = d;
      },
      closeDialog: function () { this.dlg = null; },
      dieValue: function () {
        var die = this.dlg && this.dlg.npc.action_dice[this.dlg.die];
        return die ? die.value : "?";
      },
      dialogTitle: function () {
        if (!this.dlg) return "";
        var titles = {
          menu: "What does " + this.dlg.npc.name + " do?",
          attack: this.dlg.npc.name + ": " + (this.dlg.attack ? this.dlg.attack.label : "Attack"),
          parry: this.dlg.npc.name + ": Parry",
          other: this.dlg.npc.name + ": Something else",
          damage: this.dlg.npc.name + " took damage",
          down: this.dlg.npc.name + " is down",
          adjust: "Adjust " + this.dlg.npc.name,
          rebuild: "Rebuild " + this.dlg.npc.name,
          rename: "Rename " + this.dlg.npc.name,
        };
        return titles[this.dlg.kind] || "";
      },

      chooseAttack: function (atk) {
        this.dlg.kind = "attack";
        this.dlg.attack = atk;
        this.dlg.step = "target";
      },
      chooseTarget: function (pc) {
        this.dlg.target = pc;
        this.dlg.tn = pc ? pc.tn_to_be_hit : null;
        this.dlg.parrySkill = pc ? pc.parry : 0;
        this.dlg.step = "roll";
      },
      rollAttack: async function () {
        var d = this.dlg;
        var body = { roll_key: d.attack.key, die: d.die, tn: d.tn, void: d.void || 0 };
        if (d.target) body.target_id = d.target.id;
        var data = await this.post("/npcs/" + d.npc.id + "/attack", body);
        if (data === null) return;
        d.result = data;
        d.parry = "none";
        d.weapon = "katana";
        d.damage = null;
        d.step = "result";
      },
      rollDamage: async function () {
        var d = this.dlg;
        var body = { parry: d.parry, weapon: d.weapon };
        if (d.parry === "failed") body.parry_skill = d.parrySkill;
        var data = await this.post("/actions/" + d.result.action_id + "/damage", body);
        if (data === null) return;
        d.damage = data.outcome === "parried" ? "parried" : data.damage;
      },
      rollParry: async function () {
        var d = this.dlg;
        var dice = [d.die];
        if (d.interrupt) {
          if (d.secondDie === null || d.secondDie === "") { d.error = "Pick the second die"; return; }
          dice.push(Number(d.secondDie));
        }
        var body = { dice: dice, attack_total: d.attackTotal, void: d.void || 0,
                     predeclared: !!d.predeclared };
        if (d.attacker) body.attacker_id = Number(d.attacker);
        var data = await this.post("/npcs/" + d.npc.id + "/parry", body);
        if (data !== null) d.result = data;
      },
      doOther: async function () {
        var d = this.dlg;
        var data = await this.post("/npcs/" + d.npc.id + "/other", { die: d.die, label: d.label });
        if (data !== null) this.closeDialog();
      },
      takeDamage: async function () {
        var d = this.dlg;
        var data = await this.post("/npcs/" + d.npc.id + "/take-damage",
                                   { amount: d.amount, void: d.void || 0 });
        if (data === null) return;
        d.result = data;
        if (data.down_prompt) this.promptDown(d.npc);
      },
      woundCheckText: function () {
        var r = this.dlg.result;
        if (r.passed) return "Wound check " + r.total + " vs " + r.light_wounds + " - passed";
        return "Wound check " + r.total + " vs " + r.light_wounds + " - failed, " +
          r.serious_wounds_taken + " serious wound" + (r.serious_wounds_taken === 1 ? "" : "s");
      },
      keepLightWounds: function () { this.dlg.chosen = true; this.closeDialog(); },
      takeSeriousWound: async function () {
        var npc = this.dlg.npc;
        var data = await this.post("/npcs/" + npc.id + "/take-serious-wound");
        if (data === null) return;
        this.dlg.chosen = true;
        if (data.down_prompt) this.promptDown(npc); else this.closeDialog();
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
