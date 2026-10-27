// The Night's Rest date picker's pure helpers (app/static/js/rest_date.js).
const test = require('node:test');
const assert = require('node:assert');
const {previousText, restDateBody} = require('../../app/static/js/rest_date.js');

const when = iso => 'T' + iso;
const dated = (month, day, label, at) => ({created_at: at, game_date: {month, day, label}});

test('restDateBody: neither, both, or an error for one', () => {
    assert.deepStrictEqual(restDateBody('', ''), {});
    assert.deepStrictEqual(restDateBody('3', '14'), {game_month: 3, game_day: 14});
    assert.ok(restDateBody('3', '').error);
    assert.ok(restDateBody('', '14').error);
});

test('previousText: no rests', () => {
    assert.strictEqual(previousText(null, 'Previous rest', when), 'No Night\'s Rest recorded yet.');
    assert.strictEqual(previousText({previous: null}, 'Previous rest', when), 'No Night\'s Rest recorded yet.');
});

test('previousText: a dated previous rest', () => {
    const cal = {previous: dated(3, 14, '14th day of the 3rd month (Yayoi)', 'a'), last_dated: null};
    assert.strictEqual(previousText(cal, 'Previous rest', when),
        'Previous rest: 14th day of the 3rd month (Yayoi) (Ta).');
});

test('previousText: an undated previous rest names the last dated one', () => {
    const cal = {
        previous: {created_at: 'b', game_date: null},
        last_dated: dated(3, 14, '14th day of the 3rd month (Yayoi)', 'a'),
    };
    assert.strictEqual(previousText(cal, 'Latest rest', when),
        'Latest rest: no in-game night given (Tb). Last dated: 14th day of the 3rd month (Yayoi) (Ta).');
});

test('ordinal matches game_calendar.ordinal', () => {
    const {ordinal} = require('../../app/static/js/rest_date.js');
    assert.deepStrictEqual([1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 30].map(ordinal),
        ['1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '23rd', '30th']);
});
