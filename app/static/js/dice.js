/* L7R dice rolling: rolls dice with reroll-10s, animates a tray of dice,
 * and plays synthesized sounds via Web Audio API. The Alpine "diceRoller"
 * component on the character sheet calls into these helpers.
 *
 * Exports (attached to window):
 *   rollD10()                                  -> int 1..10
 *   rollOneDie(rerollTens)                     -> {parts:int[], value:int}
 *   rollAllDice(rolled, rerollTens)            -> [{parts, value}, ...]
 *   rollAndAnimate(rolled, rerollTens, anim)   -> Promise<dice[]>
 *   playDiceSound(numDice)
 */

(function () {
    'use strict';

    function rollD10() {
        return Math.floor(Math.random() * 10) + 1;
    }

    function rollOneDie(rerollTens) {
        const parts = [];
        let v = rollD10();
        parts.push(v);
        if (rerollTens) {
            while (v === 10) {
                v = rollD10();
                parts.push(v);
            }
        }
        const value = parts.reduce((a, b) => a + b, 0);
        return { parts, value };
    }

    function rollAllDice(rolled, rerollTens) {
        const out = [];
        for (let i = 0; i < rolled; i++) {
            out.push(rollOneDie(rerollTens));
        }
        return out;
    }

    // ----------------------------------------------------------------------
    // Animation
    // ----------------------------------------------------------------------

    // SVG namespace for createElementNS — required for SVG elements to render.
    const SVG_NS = 'http://www.w3.org/2000/svg';

    // d10 kite face. Top apex angle 70° (visibly blunt, no longer "pointy"),
    // with the other three angles at 96.67° each (sum = 360°). This produces
    // a kite that is much wider and shorter than the strict mathematical
    // pentagonal-trapezohedron face but still clearly kite-shaped.
    //
    // Underlying vertices (in viewBox units):
    //   T = (50, 0), R = (100, 71.4), B = (50, 116), L = (0, 71.4)
    //
    // The visible shape is a <path> with quadratic Bezier curves at each
    // vertex (radius r = 8) so the corners are softly rounded instead of
    // coming to sharp points. The control point of each curve is the
    // original kite vertex.
    const DIE_VIEWBOX = '0 0 100 116';
    const DIE_PATH_D = (
        'M 54.59 6.55 ' +
        'L 95.41 64.85 ' +
        'Q 100 71.4 94.03 76.73 ' +
        'L 55.97 110.67 ' +
        'Q 50 116 44.03 110.67 ' +
        'L 5.97 76.73 ' +
        'Q 0 71.4 4.59 64.85 ' +
        'L 45.41 6.55 ' +
        'Q 50 0 54.59 6.55 ' +
        'Z'
    );

    // Display convention: a 10 shows as "0" on a real d10. The internal
    // value used for kept-set calculation, totalling, and the result-pool
    // view is still 10.
    function dieFaceText(value) {
        return value === 10 ? '0' : String(value);
    }

    function makeDieEl(value, extraClass) {
        const svg = document.createElementNS(SVG_NS, 'svg');
        svg.setAttribute('viewBox', DIE_VIEWBOX);
        svg.classList.add('die');
        if (extraClass) {
            extraClass.split(' ').forEach(c => { if (c) svg.classList.add(c); });
        }
        const path = document.createElementNS(SVG_NS, 'path');
        path.setAttribute('d', DIE_PATH_D);
        path.classList.add('die-shape');
        svg.appendChild(path);

        const text = document.createElementNS(SVG_NS, 'text');
        // Centred horizontally; vertically near the kite centroid (~y=65
        // in the new 116-unit viewBox).
        text.setAttribute('x', '50');
        text.setAttribute('y', '65');
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('dominant-baseline', 'middle');
        text.classList.add('die-text');
        text.textContent = dieFaceText(value);
        svg.appendChild(text);

        return svg;
    }

    function setDieValue(svg, value) {
        const text = svg.querySelector('.die-text');
        if (text) text.textContent = dieFaceText(value);
    }

    // Each "round" of animation (initial roll, or one reroll wave) lasts
    // ~2 seconds: dice tumble for ROLLING_MS, then settle and stay visible
    // for SETTLE_MS so the user can read the values before the next round
    // (or before the modal swaps to the result panel).
    const ROLLING_MS = 1300;
    const SETTLE_MS = 800;

    async function rollAndAnimate(rolled, rerollTens, animate, playSound) {
        const dice = rollAllDice(rolled, rerollTens);
        if (!animate) {
            // No animation, but still play one sound burst if enabled.
            if (playSound) playSound(rolled);
            return dice;
        }

        const tray = document.getElementById('dice-animation');
        if (!tray) return dice;
        tray.innerHTML = '';

        // Create one rolling die per die in the roll. Show only the first
        // (initial) value for now; rerolls animate later.
        const cells = [];
        for (let i = 0; i < dice.length; i++) {
            const cell = document.createElement('div');
            cell.className = 'die-cell';
            const top = makeDieEl('?', 'rolling');
            cell.appendChild(top);
            tray.appendChild(cell);
            cells.push({ cell, dice: [top] });
        }

        // Round 1: initial roll
        if (playSound) playSound(dice.length);
        await sleep(ROLLING_MS);

        // Settle each die's first value
        for (let i = 0; i < dice.length; i++) {
            const initial = dice[i].parts[0];
            const cell = cells[i];
            cell.dice[0].classList.remove('rolling');
            setDieValue(cell.dice[0], initial);
            if (initial === 10) {
                cell.dice[0].classList.add('is-ten');
            }
        }
        await sleep(SETTLE_MS);

        // Each subsequent round: animate one reroll layer for any 10s
        const maxParts = Math.max(...dice.map(d => d.parts.length));
        for (let depth = 1; depth < maxParts; depth++) {
            // How many dice are getting a reroll this round
            const rerollCount = dice.filter(d => d.parts.length > depth).length;
            if (playSound && rerollCount > 0) playSound(rerollCount);

            for (let i = 0; i < dice.length; i++) {
                if (dice[i].parts.length > depth) {
                    const cell = cells[i];
                    const newDie = makeDieEl('?', 'rolling reroll');
                    cell.cell.appendChild(newDie);
                    cell.dice.push(newDie);
                }
            }
            await sleep(ROLLING_MS);
            for (let i = 0; i < dice.length; i++) {
                if (dice[i].parts.length > depth) {
                    const cell = cells[i];
                    const die = cell.dice[depth];
                    die.classList.remove('rolling');
                    setDieValue(die, dice[i].parts[depth]);
                    if (dice[i].parts[depth] === 10) {
                        die.classList.add('is-ten');
                    }
                }
            }
            await sleep(SETTLE_MS);
        }

        return dice;
    }

    function sleep(ms) {
        return new Promise(r => setTimeout(r, ms));
    }

    // ----------------------------------------------------------------------
    // Sound (Web Audio API, synthesized)
    // ----------------------------------------------------------------------

    let audioCtx = null;

    function getAudioCtx() {
        if (audioCtx) return audioCtx;
        try {
            const Ctor = window.AudioContext || window.webkitAudioContext;
            if (!Ctor) return null;
            audioCtx = new Ctor();
        } catch (err) {
            console.warn('AudioContext init failed:', err);
            audioCtx = null;
        }
        return audioCtx;
    }

    function playClick(ctx, when, dur, gain) {
        // Short noise burst with a fast envelope, like a die hitting wood.
        const sampleRate = ctx.sampleRate;
        const length = Math.max(1, Math.floor(sampleRate * dur));
        const buffer = ctx.createBuffer(1, length, sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < length; i++) {
            data[i] = (Math.random() * 2 - 1) * (1 - i / length);
        }
        const src = ctx.createBufferSource();
        src.buffer = buffer;

        const filter = ctx.createBiquadFilter();
        filter.type = 'lowpass';
        filter.frequency.value = 2400;
        filter.Q.value = 0.6;

        const g = ctx.createGain();
        g.gain.setValueAtTime(0, when);
        g.gain.linearRampToValueAtTime(gain, when + 0.005);
        g.gain.exponentialRampToValueAtTime(0.001, when + dur);

        src.connect(filter).connect(g).connect(ctx.destination);
        src.start(when);
        src.stop(when + dur);
    }

    function playDiceSound(numDice) {
        const ctx = getAudioCtx();
        if (!ctx) return;
        if (ctx.state === 'suspended') {
            ctx.resume().catch(() => {});
        }
        const t0 = ctx.currentTime + 0.01;
        // Sounds are designed to fill the ~1.7s rolling phase of one round.
        if (numDice <= 1) {
            // A single sustained "thoonk" instead of a click
            playClick(ctx, t0, 0.6, 0.4);
        } else if (numDice === 2) {
            // Two distinct hits over the round
            playClick(ctx, t0, 0.5, 0.36);
            playClick(ctx, t0 + 0.7, 0.5, 0.36);
        } else {
            // Continuous rattle stretched across the rolling phase (~1.6s)
            const totalDuration = 1.6;
            const count = Math.min(24, 8 + numDice);
            for (let i = 0; i < count; i++) {
                const offset = (i / count) * totalDuration + Math.random() * 0.06;
                const dur = 0.15 + Math.random() * 0.12;
                const gain = 0.18 + Math.random() * 0.2;
                playClick(ctx, t0 + offset, dur, gain);
            }
        }
    }

    // ----------------------------------------------------------------------
    // Export
    // ----------------------------------------------------------------------
    window.L7RDice = {
        rollD10,
        rollOneDie,
        rollAllDice,
        rollAndAnimate,
        playDiceSound,
    };
})();
