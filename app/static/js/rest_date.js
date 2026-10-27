// The Night's Rest in-game date picker (partials/rest_date_picker.html),
// shared by the sheet's Night's Rest modals and the GM's Rest page.
//
// The picker is a nested Alpine component: it reads and writes its parent's
// `restMonth` / `restDay` (strings, '' for none), `restCalendar` (the
// server's rest_calendar_state) and `restDateError`, so each parent only
// declares those and sends restDateBody(month, day) with its POST.
(function () {
    function ordinal(n) {
        // 1 -> "1st", 11 -> "11th", 23 -> "23rd" (game_calendar.ordinal's twin).
        const t = n % 100;
        if (t >= 10 && t <= 20) return n + 'th';
        return n + ({1: 'st', 2: 'nd', 3: 'rd'}[n % 10] || 'th');
    }

    function formatWhen(iso) {
        // "Mon Oct 19, 9:42pm" in the viewer's own time zone.
        const d = new Date(iso);
        const day = d.toLocaleDateString(undefined, {weekday: 'short', month: 'short', day: 'numeric'});
        let h = d.getHours();
        const m = String(d.getMinutes()).padStart(2, '0');
        const ampm = h >= 12 ? 'pm' : 'am';
        h = h % 12 || 12;
        return day + ', ' + h + ':' + m + ampm;
    }

    // The line beside "Next night": the previous rest, and when it was not
    // dated, the last one that was (which "Next night" counts from).
    function previousText(cal, prefix, when) {
        when = when || formatWhen;
        const prev = cal && cal.previous;
        if (!prev) return 'No Night\'s Rest recorded yet.';
        let text = prefix + ': '
            + (prev.game_date ? prev.game_date.label : 'no in-game night given')
            + ' (' + when(prev.created_at) + ')';
        const dated = cal.last_dated;
        if (dated && dated.game_date) {
            text += '. Last dated: ' + dated.game_date.label + ' (' + when(dated.created_at) + ')';
        }
        return text + '.';
    }

    // {game_month, game_day} for the POST body, {} for no night, or
    // {error} when only one of the two is chosen.
    function restDateBody(month, day) {
        if (!month && !day) return {};
        if (!month || !day) return {error: 'Pick both a month and a day, or neither.'};
        return {game_month: parseInt(month, 10), game_day: parseInt(day, 10)};
    }

    function restDatePicker(months, prefix) {
        return {
            months: months,
            days() {
                const m = this.months[parseInt(this.restMonth, 10) - 1];
                return m ? m.days : [];
            },
            monthChanged() {
                if (!this.restMonth) this.restDay = '';
                this.restDateError = '';
            },
            useNextNight() {
                const n = this.restCalendar && this.restCalendar.next_night;
                if (!n) return;
                this.restMonth = String(n.month);
                this.restDay = String(n.day);
                this.restDateError = '';
            },
            nextNightLabel() {
                const n = this.restCalendar && this.restCalendar.next_night;
                return n ? 'Next night: ' + n.label : 'Next night';
            },
            previousLine() { return previousText(this.restCalendar, prefix); },
        };
    }

    const api = {ordinal, formatWhen, previousText, restDateBody, restDatePicker};
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (typeof window !== 'undefined') {
        window.L7RRestDate = api;
        window.restDatePicker = restDatePicker;
    }
})();
