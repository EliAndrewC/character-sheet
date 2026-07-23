/*
 * Pure, framework-free roll-math helpers.
 *
 * Why this file exists: a chunk of L7R school/roll math used to live inline in
 * the sheet's Alpine layer (diceRoller()/trackingData()/freeformRoller() and
 * the roll modals). Embedded inside `@click` handlers it could only be
 * exercised by a full-browser e2e clicktest. Pulling the *pure arithmetic* out
 * here lets it be reasoned about - and unit-tested in ~0.2s with `node --test`
 * - in isolation. The Alpine layer keeps the *interaction* (when to apply,
 * accumulate, undo, optimistic display); the *arithmetic* lives here.
 *
 * Rules for this file:
 *   - Pure only: inputs -> value, deterministic, NO DOM/Alpine/`this`/side
 *     effects. If you need Alpine state, pass it in as an argument.
 *   - Every function must be covered (line + branch) by tests/js/roll_math.test.js.
 *     `node --test --experimental-test-coverage tests/js/` must report 100% on
 *     this file.
 *   - Exposed as `globalThis.L7RRollMath` (window in the browser; loaded before
 *     Alpine via base.html) AND `module.exports` for the Node test runner.
 */
(function () {
  "use strict";

  var L7RRollMath = {
    /** max(0, x) - clamp a value to non-negative. */
    clampNonNegative: function (x) {
      return Math.max(0, x);
    },

    // ----------------------------------------------------------------- //
    // Group A - wound checks                                            //
    // ----------------------------------------------------------------- //

    /**
     * Effective light wounds for serious-wound distribution. Bayushi Bushi 5th
     * Dan halves light wounds (round down) for this purpose; everyone else uses
     * the raw value.
     */
    woundCheckEffectiveLw: function (lightWounds, bayushiHalfLw) {
      return bayushiHalfLw ? Math.floor(lightWounds / 2) : lightWounds;
    },

    /**
     * Resolve a wound check. Pass iff rollTotal >= lightWounds. On failure the
     * margin is how far the roll fell short of the *effective* light wounds
     * (Bayushi-halved if applicable), clamped at 0, and the inflicted serious
     * wounds are floor(margin / 10) + 1.
     *
     * @returns {{passed: boolean, margin: number, seriousWounds: number}}
     */
    woundCheckResult: function (rollTotal, lightWounds, bayushiHalfLw) {
      if (rollTotal >= lightWounds) {
        return { passed: true, margin: rollTotal - lightWounds, seriousWounds: 0 };
      }
      var effLw = bayushiHalfLw ? Math.floor(lightWounds / 2) : lightWounds;
      var margin = Math.max(0, effLw - rollTotal);
      return { passed: false, margin: margin, seriousWounds: Math.floor(margin / 10) + 1 };
    },

    /** Max serious wounds a single failed check can inflict at this LW. */
    woundCheckMaxSeriousWounds: function (effectiveLw) {
      return Math.floor(effectiveLw / 10) + 1;
    },

    // ----------------------------------------------------------------- //
    // Group B - attack / contest                                        //
    // ----------------------------------------------------------------- //

    /** Double attacks raise the to-hit TN by 20. */
    attackEffectiveTn: function (baseTn, isDoubleAttack) {
      return isDoubleAttack ? baseTn + 20 : baseTn;
    },

    /** Extra damage dice from beating a TN: one per full 5 points of excess. */
    excessToExtraDice: function (excess) {
      return excess > 0 ? Math.floor(excess / 5) : 0;
    },

    /**
     * Doji Artisan 5th Dan bonus shape: floor((value - 10) / 5), clamped at 0.
     * Used keyed on the attack TN, the wound-check light wounds, and the
     * opponent's contested result (all the same arithmetic).
     */
    bonusPer5Over10: function (value) {
      return Math.max(0, Math.floor((value - 10) / 5));
    },

    /** Implied parry skill from a chosen TN: (TN - 5) / step, min 1. */
    parrySkillFromTn: function (tn, tnStep) {
      return Math.max(1, Math.floor((tn - 5) / tnStep));
    },

    /**
     * Parry probability-chart target. A parry succeeds when the roll total
     * meets or beats the attacker's TN, so the kept-dice total needs to reach
     * TN minus every flat bonus folded into the roll (formula flat, the
     * predeclared +5, per-VP combat flat bonuses, etc.). Clamped at 0 so the
     * probability lookup never indexes a negative target.
     */
    parryEffectiveTarget: function (tn, flat) {
      return Math.max(0, tn - flat);
    },

    /** +10 per checked Attack Specialization. */
    attackSpecBonus: function (checkedCount) {
      return 10 * checkedCount;
    },

    /** Free raises (penalty) imposed by an oppose-roll result: floor(result/5). */
    freeRaisesFromResult: function (rollTotal) {
      return Math.floor(rollTotal / 5);
    },

    // ----------------------------------------------------------------- //
    // Group C - damage / dice cap                                       //
    // ----------------------------------------------------------------- //

    /**
     * L7R 10k10 cap. Rolled dice past 10 convert to kept dice; kept dice past
     * 10 convert to +2 flat each. Order matters: cap rolled first, then kept.
     * @returns {{rolled, kept, flat, overflowFlat}} - overflowFlat is just the
     *   +2-per-die kept-overflow contribution (for labeling).
     */
    applyDiceCap: function (rolled, kept, flat) {
      var overflowFlat = 0;
      if (rolled > 10) {
        kept += rolled - 10;
        rolled = 10;
      }
      if (kept > 10) {
        overflowFlat = 2 * (kept - 10);
        flat += overflowFlat;
        kept = 10;
      }
      return { rolled: rolled, kept: kept, flat: flat, overflowFlat: overflowFlat };
    },

    /**
     * Ceiling on a roll's *result* (not its dice), e.g. Withdrawn's "your
     * etiquette and open sincerity rolls are never considered to be higher
     * than 15". `maxTotal` is RollFormula.max_total, where 0 means "no cap".
     *
     * Callers must apply this at display time rather than baking it into
     * baseTotal: post-roll spends (free raises, Conviction, Mirumoto points)
     * mutate baseTotal after the roll resolves, and a one-shot cap would be
     * undone by the next `baseTotal += 5`. The roll is never *considered*
     * higher than the cap, so the ceiling has to outlive those spends.
     */
    applyTotalCap: function (total, maxTotal) {
      if (typeof maxTotal !== "number" || !(maxTotal > 0)) return total;
      return Math.min(total, maxTotal);
    },

    /** True iff a cap exists and is actually lowering `total`. */
    totalCapApplies: function (total, maxTotal) {
      if (typeof maxTotal !== "number" || !(maxTotal > 0)) return false;
      return total > maxTotal;
    },

    /**
     * The ceiling binding one "Alternative totals" row. A row may carry its
     * own (Withdrawn caps *open* sincerity rolls, while the formula's base
     * contested roll is uncapped); otherwise it inherits the formula's, since
     * a conditional bonus on a capped roll is still that capped roll.
     * Returns 0 when uncapped.
     */
    altCap: function (alt, formulaMaxTotal) {
      var own = (alt || {}).max_total;
      if (typeof own === "number") return own;
      return typeof formulaMaxTotal === "number" ? formulaMaxTotal : 0;
    },

    /** One alternative row's displayed value: base + delta, capped. */
    altTotal: function (baseTotal, alt, formulaMaxTotal) {
      var extra = ((alt || {}).extra_flat) || 0;
      return this.applyTotalCap(
        baseTotal + extra, this.altCap(alt, formulaMaxTotal)
      );
    },

    /**
     * The "if all of the above" row. Any capped component makes the combined
     * row an instance of that capped condition too, so the tightest cap among
     * the rows binds.
     */
    altTotalAll: function (baseTotal, alts, formulaMaxTotal) {
      var rows = alts || [];
      var self = this;
      var sum = rows.reduce(function (s, a) {
        return s + ((a || {}).extra_flat || 0);
      }, 0);
      var caps = rows
        .map(function (a) { return self.altCap(a, formulaMaxTotal); })
        .filter(function (c) { return c > 0; });
      var cap = caps.length ? Math.min.apply(Math, caps) : 0;
      return this.applyTotalCap(baseTotal + sum, cap);
    },

    /**
     * The alternative rows worth rendering. A row whose capped value equals
     * the roll's own displayed (capped) total conveys nothing - Withdrawn's
     * etiquette cap swallows a conditional bonus like Streetwise's, leaving
     * a row that just repeats the only total - so it is dropped. Callers
     * hide the whole "Alternative totals" section when this comes back
     * empty, and feed the survivors to altTotalAll.
     */
    visibleAlternatives: function (baseTotal, alts, formulaMaxTotal) {
      var self = this;
      var displayed = this.applyTotalCap(baseTotal, formulaMaxTotal);
      return (alts || []).filter(function (a) {
        return a && self.altTotal(baseTotal, a, formulaMaxTotal) !== displayed;
      });
    },

    /**
     * Kakita 5th Dan contested-damage dice adjustment: +/- floor(|diff| / 5),
     * rounded toward zero (so a negative diff truncates toward 0, not down).
     */
    damageDiceContestAdjust: function (diff) {
      if (diff >= 0) return Math.floor(diff / 5);
      return -Math.floor(-diff / 5) || 0; // `|| 0` avoids -0 for small negatives
    },

    /**
     * A failed parry reduces the attacker's extra damage dice by the parry
     * skill - fully ("full"), by half rounded down ("half", Mirumoto 4th Dan),
     * or not at all ("none", Brotherhood 4th Dan). Never below 0.
     */
    failedParryDiceReduction: function (totalExtra, parrySkill, mode) {
      if (mode === "none") return totalExtra;
      var reduce = mode === "half" ? Math.floor(parrySkill / 2) : parrySkill;
      return Math.max(0, totalExtra - reduce);
    },

    /** Otaku 5th Dan: trade dice for an auto serious wound, never below 2 rolled. */
    tradeDiceFloor: function (rolled, tradeDice) {
      return Math.max(2, rolled - tradeDice);
    },

    // ----------------------------------------------------------------- //
    // Group D - per-school banked / phase math                          //
    // ----------------------------------------------------------------- //

    /** Phases an action die was held: max(0, phase - dieValue). */
    shinjoPhasesHeld: function (phase, dieValue) {
      return Math.max(0, phase - dieValue);
    },

    /** Shinjo Bushi: +2 per phase the spent action die was held. */
    shinjoPhaseBonus: function (phase, dieValue) {
      return 2 * Math.max(0, phase - dieValue);
    },

    /**
     * Kakita Duelist 3rd Dan: X * (defenderPhase - attackerPhase), clamped at 0,
     * where X is the attack skill. The 5th-Dan / phase-0-interrupt paths pass
     * attackerPhase = 0.
     */
    kakitaDefenderPhaseBonus: function (x, defenderPhase, attackerPhase) {
      return x * Math.max(0, defenderPhase - attackerPhase);
    },

    /** Contested-roll free raises: +5 per rank your skill exceeds theirs. */
    contestSkillRaiseBonus: function (ourRank, theirRank) {
      return Math.max(0, ourRank - theirRank) * 5;
    },

    /** Bank the excess of our roll over the opponent's, clamped at 0. */
    bankExcess: function (ourRoll, opponentRoll) {
      return Math.max(0, ourRoll - opponentRoll);
    },

    /** Yogo Warden 3rd Dan: heal light wounds by vpSpent * healPerVp, min 0. */
    yogoHealLightWounds: function (lightWounds, vpSpent, healPerVp) {
      return Math.max(0, lightWounds - vpSpent * healPerVp);
    },

    // ----------------------------------------------------------------- //
    // Group E - thresholds / misc                                       //
    // ----------------------------------------------------------------- //

    /** Impaired (loses reroll-10s) when serious wounds >= Earth ring. */
    isImpaired: function (seriousWounds, earthRing) {
      return seriousWounds >= earthRing;
    },

    /**
     * Sum of the highest ``k`` values in ``values`` (a kept-dice pool). Used
     * when recomputing a roll after a PCP "reroll 10s while impaired" explodes
     * some dice and may change which dice are kept. ``k`` is clamped to the
     * pool size; a non-positive ``k`` keeps nothing.
     */
    keepHighestSum: function (values, k) {
      if (!(k > 0)) return 0;
      var sorted = values.slice().sort(function (a, b) { return a - b; });
      var kept = sorted.slice(Math.max(0, sorted.length - k));
      return kept.reduce(function (a, b) { return a + b; }, 0);
    },

    /**
     * PCP "reroll 10s while impaired" (rules/10). The impaired roll's 10s never
     * exploded, so this is NOT a full reroll: KEEP every die and let each one
     * showing a 10 explode (reroll-and-add). ``dice`` is the rolled pool
     * ([{value, parts?}]); ``rerolls`` are the exploding rerolls ({value, parts})
     * for the 10s, in order; ``keptCount`` is how many dice are kept. A 10 whose
     * reroll chain is [10, 3] (value 13) becomes 10 + 13 = 23 with parts
     * [10, 10, 3]. Returns {dice: [{value, parts, kept}], keptSum} with the
     * highest ``keptCount`` dice flagged kept.
     */
    pcpExplodeTens: function (dice, rerolls, keptCount) {
      var out = [], ri = 0;
      for (var i = 0; i < dice.length; i++) {
        var d = dice[i];
        if (d.value === 10) {
          var rr = rerolls[ri++] || { value: 0, parts: [] };
          var chain = (rr.parts && rr.parts.length) ? rr.parts : [rr.value];
          out.push({ value: 10 + rr.value, parts: [10].concat(chain), kept: false });
        } else {
          out.push({
            value: d.value,
            parts: (d.parts && d.parts.length) ? d.parts.slice() : [d.value],
            kept: false,
          });
        }
      }
      var keptSum = this.keepHighestSum(out.map(function (d) { return d.value; }), keptCount);
      // Flag the highest ``keptCount`` dice as kept (same ordering keepHighestSum
      // sums, so the flagged dice and keptSum always agree).
      var order = out
        .map(function (d, i) { return { i: i, v: d.value }; })
        .sort(function (a, b) { return a.v - b.v; });
      var keep = Math.max(0, Math.min(keptCount, out.length));
      for (var k = order.length - keep; k < order.length; k++) {
        out[order[k].i].kept = true;
      }
      return { dice: out, keptSum: keptSum };
    },

    /**
     * Player Character Point cost math. The Nth PCP a character spends costs
     * N XP, so ``count`` spends total to the Nth triangular number.
     * See rules/10-player_character_points.md and services/xp.pcp_total_cost.
     */
    pcpTotalCost: function (count) {
      var n = Math.max(0, Math.floor(count || 0));
      return (n * (n + 1)) / 2;
    },

    /** XP cost of the next (count+1th) PCP spend. */
    pcpNextCost: function (count) {
      return Math.max(0, Math.floor(count || 0)) + 1;
    },

    /**
     * Split a PCP's XP cost into the part drawn from unspent XP and the part
     * that goes into XP debt (future earned XP). ``remainingBefore`` may be
     * negative (already in debt), in which case the whole cost deepens it.
     * Returns {fromUnspent, fromDebt, remainingAfter}; the two parts sum to
     * ``cost``.
     */
    pcpSpendBreakdown: function (remainingBefore, cost) {
      var fromUnspent = Math.max(0, Math.min(remainingBefore, cost));
      return {
        fromUnspent: fromUnspent,
        fromDebt: cost - fromUnspent,
        remainingAfter: remainingBefore - cost,
      };
    },

    /** Iaijutsu duel TN = total XP / 10 (round down). */
    duelTn: function (totalXp) {
      return Math.floor(totalXp / 10);
    },

    /**
     * Iaijutsu "Evaluate Stance" (duel stance phase). An open iaijutsu roll
     * kept with Air discerns the opponent's Fire Ring and starting TN to be
     * hit. Per the combat rules: it tells you the opponent has at least X
     * Fire, where X is your roll / 5 (rounded down); if X exceeds their Fire
     * you know it exactly. The TN is discerned the same way but on the roll's
     * own scale - you learn it exactly if your roll exceeds it, otherwise only
     * that it is at least your roll.
     *
     * ``maxRing`` is the highest Fire Ring an opponent could have (defaults to
     * RING_MAX_SCHOOL = 6, the cap when Fire is a school ring). Once the lower
     * bound reaches that cap, "at least the cap" pins the value exactly, so the
     * exact Fire Ring is always known - reported via ``fireCertain``.
     *
     * @returns {{roll, fireBound, fireExactMax, fireCertain, tnBound, tnExactMax}}
     *   fireBound    - opponent's Fire is known to be at least this.
     *   fireExactMax - exact Fire learned iff their Fire is <= this (= bound-1).
     *   fireCertain  - exact Fire is guaranteed (bound >= the ring cap).
     *   tnBound      - opponent's TN is known to be at least this (= the roll).
     *   tnExactMax   - exact TN learned iff their TN is <= this (= roll-1).
     */
    evaluateStanceInfo: function (rollTotal, maxRing) {
      var r = Math.max(0, Math.floor(rollTotal || 0));
      var cap = maxRing || 6; // RING_MAX_SCHOOL: highest Fire an opponent has
      var fireBound = Math.floor(r / 5);
      return {
        roll: r,
        fireBound: fireBound,
        fireExactMax: fireBound - 1,
        fireCertain: fireBound >= cap,
        tnBound: r,
        tnExactMax: r - 1,
      };
    },

    // ----------------------------------------------------------------- //
    // Group F - iaijutsu duel focus/strike odds chart                    //
    //                                                                    //
    // The focus/strike phase shows hit / damage / serious-wound          //
    // estimates with NO void or discretionary adjustments: none can be   //
    // spent during the strike (own Conviction is ignored here as an      //
    // edge case). Strike rolls and their wound checks do not reroll 10s; //
    // the resulting damage rolls do. All functions work from "survival   //
    // arrays" where survival[x] = P(kept-dice total >= x), the same      //
    // no-reroll slices the server ships for the wound check modal.       //
    // ----------------------------------------------------------------- //

    /** P(kept total >= x) with out-of-range indices clamped to 1 / 0. */
    survivalAt: function (survival, x) {
      if (x <= 0) return 1;
      if (!survival || x >= survival.length) return 0;
      return survival[x];
    },

    /**
     * Average iaijutsu-duel damage roll for a given strike excess. In a
     * duel every point of excess adds a rolled die (not one per 5). The
     * pool is (weaponRolled + ringVal + extraRolled + excess) k
     * (weaponKept + extraKept) + dmgFlat, 10k10-capped; dmgAvgs maps
     * "rolled,kept" to the average kept sum WITH 10s rerolled (damage
     * rolls keep their rerolls even in duels).
     */
    duelDamageAvg: function (dmg, excess, dmgAvgs) {
      var capped = this.applyDiceCap(
        (dmg.weaponRolled || 0) + (dmg.ringVal || 0) + (dmg.extraRolled || 0)
          + Math.max(0, excess),
        (dmg.weaponKept || 0) + (dmg.extraKept || 0),
        dmg.dmgFlat || 0
      );
      return (dmgAvgs[capped.rolled + "," + capped.kept] || 0) + capped.flat;
    },

    /**
     * Expected serious wounds from one no-VP wound check against lw light
     * wounds, given the check's survival array and flat bonus. Counts
     * failures only (a pass inflicts 0 SW). Uses the same 10-point band
     * arithmetic as the wound check modal's probability table so the two
     * displays always agree. opts: {halfLw} Bayushi 5th Dan, {dojiWc}
     * Doji Artisan 5th Dan +1-per-5-LW-over-10.
     */
    expectedSeriousWounds: function (survival, flat, lw, opts) {
      opts = opts || {};
      if (!(lw > 0)) return 0;
      if (opts.dojiWc) flat += this.bonusPer5Over10(lw);
      var target = Math.max(0, lw - flat);
      var effLw = this.woundCheckEffectiveLw(lw, opts.halfLw);
      var effTarget = Math.max(0, effLw - flat);
      var maxSW = this.woundCheckMaxSeriousWounds(effLw);
      var expected = 0;
      for (var sw = 1; sw <= maxSW; sw++) {
        var failLo = Math.max(0, effTarget - sw * 10);
        var failHi = Math.max(0, effTarget - (sw - 1) * 10);
        var chance = this.survivalAt(survival, failLo) - this.survivalAt(survival, failHi);
        if (sw === 1 && opts.halfLw && effTarget < target) {
          chance += this.survivalAt(survival, effTarget) - this.survivalAt(survival, target);
        }
        if (chance > 0) expected += sw * chance;
      }
      return expected;
    },

    /**
     * Your strike vs an opponent TN: hit chance and average damage given
     * a hit. survival is your strike pool's no-reroll slice; flat shifts
     * every outcome (e.g. duel restart bonus).
     * @returns {{hit: number, avgDamage: number}}
     */
    duelStrikeOutcome: function (survival, flat, tn, dmg, dmgAvgs) {
      var hit = this.survivalAt(survival, tn - flat);
      if (!(hit > 0)) return { hit: 0, avgDamage: 0 };
      var sum = 0;
      for (var s = Math.max(0, tn - flat); s <= survival.length; s++) {
        var w = this.survivalAt(survival, s) - this.survivalAt(survival, s + 1);
        if (!(w > 0)) continue;
        sum += w * this.duelDamageAvg(dmg, s + flat - tn, dmgAvgs);
      }
      return { hit: hit, avgDamage: sum / hit };
    },

    /**
     * A sample opponent pool's strike vs your TN: hit chance, average
     * damage given a hit, and the average serious wounds your own
     * no-reroll wound check takes from that hit on top of your current
     * light wounds. The opponent is assumed to swing a katana (4k2) with
     * Fire equal to the sample pool's kept count and no flat bonuses.
     * The SW figure folds each excess level's AVERAGE damage into the
     * wound check (an estimate - the full damage distribution would
     * spread the bands slightly wider).
     * wc: {survival, flat, halfLw, dojiWc} - your own wound check.
     * @returns {{hit: number, avgDamage: number, avgSw: number}}
     */
    duelOpponentThreat: function (oppSurvival, tn, oppFire, dmgAvgs, wc, currentLw) {
      var hit = this.survivalAt(oppSurvival, tn);
      if (!(hit > 0)) return { hit: 0, avgDamage: 0, avgSw: 0 };
      var dmgSum = 0;
      var swSum = 0;
      for (var s = Math.max(0, tn); s <= oppSurvival.length; s++) {
        var w = this.survivalAt(oppSurvival, s) - this.survivalAt(oppSurvival, s + 1);
        if (!(w > 0)) continue;
        var d = this.duelDamageAvg(
          { weaponRolled: 4, weaponKept: 2, ringVal: oppFire, dmgFlat: 0 },
          s - tn, dmgAvgs
        );
        dmgSum += w * d;
        swSum += w * this.expectedSeriousWounds(
          wc.survival, wc.flat, currentLw + Math.round(d),
          { halfLw: wc.halfLw, dojiWc: wc.dojiWc }
        );
      }
      return { hit: hit, avgDamage: dmgSum / hit, avgSw: swSum / hit };
    },

    /**
     * Hida Bushi 3rd Dan reroll allowance: X dice (2X on counterattacks),
     * halved and rounded UP when impaired.
     */
    hidaRerollMax: function (x, isCounterattack, impaired) {
      var max = isCounterattack ? 2 * x : x;
      if (impaired) max = Math.ceil(max / 2);
      return max;
    },

    /** Round a koku amount to the nearest tenth (round half up). */
    roundToTenths: function (raw) {
      return Math.floor(raw * 10 + 0.5) / 10;
    },

    /**
     * Akodo Bushi 3rd Dan: bank floor(margin / 5) * attackSkill as a future
     * attack bonus. Returns 0 for a non-positive margin or attack skill.
     */
    akodoBankedBonus: function (margin, attackSkill) {
      if (!(margin > 0) || !(attackSkill > 0)) return 0;
      return Math.floor(margin / 5) * attackSkill;
    },

    /**
     * Lucky reroll resolution. Lucky lets you reroll and keep the better
     * result; for every roll except initiative the higher total always wins -
     * there is never a reason to keep a strictly-lower roll, so the choice is
     * automatic (no "you may keep the original" prompt). A tie keeps the
     * reroll (either is equivalent).
     *
     * Initiative is exempt: a fresh initiative roll produces a different
     * action-die layout that isn't strictly comparable, so the player keeps
     * BOTH sets and chooses per the rules. We report keepReroll=true (so the
     * fresh roll is shown as the live result) and never flag the original as
     * the auto-winner; the modal lets the player switch.
     *
     * @returns {{keepReroll: boolean, originalHigher: boolean}}
     */
    luckyResolveReroll: function (originalTotal, rerollTotal, isInitiative) {
      if (isInitiative) return { keepReroll: true, originalHigher: false };
      var originalHigher = originalTotal > rerollTotal;
      return { keepReroll: !originalHigher, originalHigher: originalHigher };
    },
  };

  // Browser: globalThis === window, so callers use window.L7RRollMath.
  globalThis.L7RRollMath = L7RRollMath;
  // Node (test runner): also export via CommonJS.
  /* node:coverage disable */
  if (typeof module !== "undefined" && module.exports) {
    module.exports = L7RRollMath;
  }
  /* node:coverage enable */
})();
