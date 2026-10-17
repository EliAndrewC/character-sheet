/* The roll distribution chart (probability-design/design.md), shared by the
 * sheet's statistics modal and the /probabilities page. Display only: every
 * number in ``view`` comes from the server (app/services/roll_stats.py).
 *
 * ``L7RRollChart.mixin()`` returns methods for an Alpine component that has a
 * ``view`` (one roll_stats view: mean, median, p10, p90, parts, bins, ...)
 * and a ``selected`` bar index. Methods, not getters: object spread would
 * freeze a getter's value. The markup is partials/roll_chart.html. */
(function () {
    function mixin() {
        return {
            bins() { return this.view?.bins || []; },
            peak() { return Math.max(0.0001, ...this.bins().map(b => b.p)); },
            // Two or three recessive lines at round percentages.
            gridLines() {
                const top = this.peak() * 100;
                const step = top > 30 ? 10 : top > 12 ? 5 : top > 5 ? 2 : 1;
                const out = [];
                for (let v = step; v <= top; v += step) out.push(v);
                return out;
            },
            meanLeft() {
                const b = this.bins();
                if (!b.length || !this.view) return 0;
                const span = (b[b.length - 1].hi + 1) - b[0].lo;
                return Math.max(0, Math.min(100, (this.view.mean - b[0].lo) / span * 100));
            },
            binLabel(b) {
                if (b.open_low) return `${b.hi} or less`;
                if (b.open_high) return `${b.lo}+`;
                return `${b.lo}-${b.hi}`;
            },
            pct(p) {
                const v = p * 100;
                if (v > 0 && v < 0.1) return '<0.1%';
                return (v >= 10 ? v.toFixed(0) : v.toFixed(1)) + '%';
            },
            // Label every bar when there are few, otherwise every other one.
            showTick(i) { return this.bins().length <= 12 || i % 2 === 0; },
            selectedBin() { return this.selected === null ? null : this.bins()[this.selected] || null; },
            // The constant parts of a total: everything but the dice, the
            // ability and the cap.
            flatParts() {
                return (this.view?.parts || []).filter(p => p.label !== 'Dice'
                    && p.label !== this.view.ability_label && !p.label.startsWith('Capped'));
            },
            fmt(v) { v = Math.round(v); return (v > 0 ? '+' : '') + v; },
        };
    }
    window.L7RRollChart = { mixin };
})();
