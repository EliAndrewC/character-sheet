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

    /** Iaijutsu duel TN = total XP / 10 (round down). */
    duelTn: function (totalXp) {
      return Math.floor(totalXp / 10);
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
