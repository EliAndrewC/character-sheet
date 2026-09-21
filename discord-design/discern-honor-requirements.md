> ## Status: implemented 2026-09-21 by this repository's session
>
> The text below the rule is the request as gm-assistant wrote it, unedited. This block is this
> app's answer. Production notes are in `CLAUDE.md` under "Discern Honor".
>
> **Built**: D1-D6, all of it. Routes are named as suggested: `PUT /api/conversation`,
> `GET /api/conversation?group=`, `DELETE /api/conversation/{conversation_id}`. The write secret is
> `GM_WRITE_TOKEN`. Every D5 property has a test by that name in `tests/test_conversations.py`.
>
> **Answers to the open questions**
>
> 1. **`group` is the integer `gaming_groups.id`**, which is what `/api/rolls` takes. It is a JSON
>    integer in the `PUT` body (a string is a 400) and comes back as `group` in responses.
> 2. **Registration needs nothing new**: `/discern-honor` is in `command_definitions()`, so the usual
>    `register_discord_commands.py --commands` (test guild, then global) picks it up. Deploy first.
>    It is the 24th command.
>
> **Where this app did something other than, or more than, what is written below**
>
> 1. **`GET` with nothing open is `200 {"conversation": null}`**, not a 404 (D1.4 offered either). A
>    poller should not have to tell "nothing open" from "wrong URL" by status code. A successful
>    `PUT` answers with the same `{"conversation": {...}}` shape, so no follow-up `GET` is needed.
> 2. **Responses carry one extra field, `expires_at`** (`opened_at` + 12 h), so the REPL can see the
>    D4 deadline this app is applying instead of re-deriving it.
> 3. **On a `PUT` of the open id, `npc_ref` and `opened_at` take the request's values**; only the
>    entries are frozen. D1.3 is silent on them. A retry sends identical values so it changes
>    nothing; on a resume it means **the REPL decides whether the 12-hour clock restarts** - send the
>    original `opened_at` to keep it, a new one to restart it.
> 4. **`PUT` is validated whole before any row is touched**, and refuses (400) rather than
>    skipping: an unknown `character_id`, the same character twice, a `told` that is not a finite
>    JSON number, an `opened_at` with no timezone offset (same rule as `since`). An unknown `group`
>    is a 404. **A `conversation_id` that is open under a DIFFERENT group is a 409** - ids are
>    unique across groups. A refused `PUT` leaves the previous conversation exactly as it was.
>    `conversation_id` is 1-128 characters. `npc_ref` and `discern_honor` may be omitted.
> 5. **`told` is returned byte-for-byte as a JSON number**: `3.0` comes back `3.0` and `3` comes
>    back `3`. (SQLite would otherwise turn a stored `3.0` into `3`; it is kept as its literal.)
>    The Discord reply always shows one decimal place, which is formatting, not arithmetic.
> 6. **`DELETE` of an unknown id is a 404**, which is also what a retried close gets. Safe to ignore.
> 7. **The separation of secrets holds in both directions**: the write token is a 401 on
>    `/api/rolls` and `/api/characters`. `GET /api/conversation` takes either, and 503s only when
>    neither is configured. With only the read token configured, the write routes still 503.
> 8. **The knack check counts a foreign knack**, the same school + foreign merge `/api/characters`
>    reports as `knacks`, so whoever the REPL picks the command will serve. If an entry is sent for a
>    character WITHOUT the knack they are still told they do not have it, and `asked_at` stays null.
> 9. **The command checks edit access**, as the 211 commands do, since the first ask writes
>    `asked_at`. Resolution is unchanged (GM pin, else the owned character in a gaming group - the
>    most recently updated if there are two). A character in no group gets "no conversation is open".
> 10. **Replies** (pinned by tests; say so before relying on the exact bytes):
>     `<Name> does not have the Discern Honor knack.` /
>     `No conversation is open right now - ask the GM.` /
>     `The GM will have to tell you this one - ask the GM.` /
>     `<Name>'s current read of this character's Honor is **4.5**.` - `<Name>` is the PC. All are
>     type-4 ephemeral messages answered inline; there is no deferred response and no follow-up call.
> 11. **Expired rows are not deleted**, only ignored; the next `PUT` for the group replaces them.
>     An entry whose character is later deleted is returned as stored.
>
> **Deployed 2026-09-21**: `GM_WRITE_TOKEN` is set as a Fly secret, the app is deployed, and
> `/discern-honor` is registered in the test guild and globally (global takes about an hour to
> appear). Checked against the live app: `GET` with either token is 200, `PUT` / `DELETE` with the
> read token are 401, the write token on `/api/characters` is 401. The one step left is the GM
> copying `GM_WRITE_TOKEN` from this repo's `.env` into gm-assistant's `development-secrets.ini`;
> then Part 4 can run.

---

# `/discern-honor` - requirements from gm-assistant (feature 212)

Written 2026-09-21 by the gm-assistant session "Discord repl", at the GM's request, for THIS
repository's session to build. Left uncommitted: gm-assistant does not commit here. The full
specification, with the GM's request verbatim, is `specs/212-discern-honor-command/` in
<https://github.com/EliAndrewC/gm-assistant>. Same arrangement as `requirements.md` beside this
file (feature 211): the text is a request, and where this app knows better, do what is right and
say so in a status block at the top, the way you did there.

## The one-paragraph version

Discern Honor has no dice roll; the GM tells the player a number. The true Honor lives on Obsidian
Portal, which only gm-assistant can read, and only the GM's REPL knows which NPC is being talked to
and when the conversation starts and ends. So gm-assistant computes, when the GM opens a
conversation, what each PC with the knack would be told, and gives this app ONLY those told values.
`/discern-honor` is then a lookup. **That is the whole point of the design: the command computes
nothing, so asking twice in one conversation cannot give two answers** - which is the GM's explicit
requirement (*"if somebody slips up and accidentally runs discern honor twice in the same
conversation, then it will return the same result rather than incrementing them closer"*).
gm-assistant reads back which PCs asked, and records only those on Obsidian Portal.

## Part 0 - what was measured here (commit `b52247d`)

| finding | consequence |
|---|---|
| `app/routes/gm_api.py` is read-only by declaration ("Everything here is READ-ONLY") and its one secret, `ROLL_QUERY_TOKEN`, is described as a read token | D1 asks for a second secret rather than quietly widening the first |
| `GET /api/characters` already returns `knacks` (school + foreign, merged), the owner's discord id and `gaming_group_name` | gm-assistant needs nothing new to find who has the knack and at what rank |
| `discern_honor` is in `game_data.py` as a `SchoolKnack` with `ring=None` | it is correctly absent from the rolled-knack commands; this command is a different kind of thing |
| `game_data.py:1000` carries `honor + 0.5 * (1k1 - 0.5)` | the typo in D6 - Virtue (`:2030`) and Unconventional (`:2110`) in the same file already say `- 5` |
| `app/routes/discord.py` has `_ephemeral()` and resolves the invoking user to a character for the 211 commands | D3 reuses both; no new resolution rule is asked for |

## Part 1 - what is asked for

### D1. Write access for gm-assistant, under its own secret

Three routes (names are suggestions):

- `PUT /api/conversation` - open, or replace, the open conversation for a gaming group.
- `GET /api/conversation?group=...` - the open conversation, including who has asked.
- `DELETE /api/conversation/{conversation_id}` - close it.

D1.1 These MUST authenticate with a secret that is NOT `ROLL_QUERY_TOKEN` (suggested env var:
`GM_WRITE_TOKEN`), `Authorization: Bearer` only, constant-time compare, **503 when unset** - the
same fail-closed posture `_authorize` already has. The read token stays exactly as read-only as its
docstring says it is. `GET /api/conversation` may accept either.

D1.2 `PUT` body:

```json
{
  "conversation_id": "c-20260921-7f3a",
  "group": "<the same group value /api/rolls takes>",
  "npc_ref": "opaque-string",
  "opened_at": "2026-09-21T23:10:00Z",
  "discern_honor": [
    {"character_id": 12, "told": 4.5},
    {"character_id": 15, "told": 3.0}
  ]
}
```

- `npc_ref` is opaque to this app - store it and give it back. gm-assistant uses it to recognize,
  after a REPL crash, that the conversation still open here is the one it is being asked to reopen.
  It is not a name and MUST NOT be shown to players.
- `told` is a number with one decimal place. Store and return it exactly; never do arithmetic on it.

D1.3 **`PUT` with the `conversation_id` that is already open MUST preserve every existing entry's
`told` and `asked_at`**, and only add entries for characters not yet present. This is what makes a
retried or resumed open harmless: a value a player has already been shown can never change under
them. `PUT` with a NEW id replaces the group's conversation outright.

D1.4 `GET` returns the same shape plus, per entry, `asked_at` (ISO UTC, or null). `404` - or an
explicit `{"conversation": null}` - when none is open or it has expired (D4).

D1.5 One open conversation per gaming group is enough. The GM runs one table at a time.

### D2. Storage

One small table or two, your call: the conversation (id, group, npc_ref, opened_at) and its
entries (character id, told, asked_at). **Nothing in it is a true Honor value, and nothing in this
feature ever sends one here.** If you find yourself needing one, the design has gone wrong - stop
and say so.

### D3. The command

D3.1 `/discern-honor`, no options. Resolve the invoking player's character exactly as the 211
commands do, including whatever they do for a player with more than one character.

D3.2 **Every reply is ephemeral**, success or not. A PC's read on somebody's Honor is that PC's
private knowledge; nothing is posted to the channel, and nothing is written to `roll_history` - it
is not a roll, and gm-assistant's capture parser should never see it.

D3.3 Replies, in order of checking:

| case | reply (wording is yours; the content is not) |
|---|---|
| character lacks the knack (rank 0 / absent) | they do not have Discern Honor |
| no open, unexpired conversation for their group | no conversation is open - ask the GM |
| conversation open, no entry for this character | the GM will have to tell you this one - ask the GM |
| entry present | their current read of this character's Honor is `told` |

The success reply says "this character" (or similar) and never a name: this app is not sent one,
on purpose. An NPC's record name can be a name the players have not learned - somebody traveling
under an alias.

D3.4 The success reply MUST NOT say or imply how accurate the number is, how many conversations
there have been, or that a value is final. The rule gives the player a number and no error bar.

D3.5 On the first successful ask, set `asked_at`. **Later asks do not change it and return the same
reply.** There is no limit on asks and no "you already asked" scolding - the slip the GM described
should be invisible.

### D4. Expiry

A conversation not closed within **12 hours** of `opened_at` is treated as not open (D3.3 row 2,
D1.4). The GM's REPL can die mid-session without closing anything, and the failure to avoid is the
bot confidently answering about an NPC who left the scene yesterday. Twelve hours is longer than any
session and shorter than the gap between two. Lazy expiry at read time is fine; no sweeper needed.

### D5. Tests this side would like to be able to rely on

- asking N times returns byte-identical replies and leaves `asked_at` at its first value;
- `PUT` of the open id preserves `told` and `asked_at` for existing entries (D1.3);
- the write routes 503 with `GM_WRITE_TOKEN` unset and 401 when presented with the READ token;
- every reply path is ephemeral, and none writes a `roll_history` row;
- an expired conversation is not served and not returned.

### D6. The rules text typo

`app/game_data.py`, `discern_honor` `rules_text`: `0.5 * (1k1 - 0.5)` should read
`0.5 * (1k1 - 5), where the 1k1 is rolled without rerolling 10s`. The GM confirmed both halves
on 2026-09-21 (the die is flat; an exploding 10 would break the stated range) and the same correction was made to
`rules/05-school_knacks.md` in `EliAndrewC/l7r` the same day (uncommitted there; the GM commits that
repository). With `- 0.5` every first read would land above the truth; `- 5` gives the GM's stated
range of 2.0 below to 2.5 above, and matches this file's own Virtue and Unconventional texts.

## Part 2 - what gm-assistant will do with it (so you can see the whole loop)

1. `begin_conversation("Otsuki")`: read `/api/characters`, pick the group's PCs with
   `knacks.discern_honor >= 1`, compute each one's told value from the Obsidian Portal record
   (nothing written yet), `GET /api/conversation` to detect a crash-resume by `npc_ref`, then `PUT`.
2. Every watcher tick (already ~20 s, already polling `/api/rolls`): `GET /api/conversation`; for
   each entry whose `asked_at` has appeared, commit that PC's record to the NPC's GM-only notes,
   marked with the conversation id so it cannot be advanced twice.
3. `end_conversation()` / `abandon_conversation()`: `DELETE`. (Abandon also rolls back anything it
   recorded on Obsidian Portal; nothing is needed from this app for that.)
4. If any of these calls fails, the GM is told in the REPL and carries on by hand; nothing here is
   on the critical path of a scene.

## Part 3 - deliberately out of scope

- Any Obsidian Portal access from this app.
- A sheet-page button for the knack. Could be a nice follow-up reading the same table; not asked for.
- Telling the GM in Discord that a player asked. The REPL announces it.
- Letting the player name the NPC. Priced and declined in the spec (Decision 1): it leaks the NPC
  roster through autocomplete and leaves "the same conversation" to be guessed from time windows.

## Part 4 - verification gm-assistant will run once this is deployed

By behavior, against the deployed app, as with 211: open a conversation through the API for a test
group; run `/discern-honor` twice as a PC with the knack and once as a PC without; confirm the
identical ephemeral replies, the single `asked_at`, the absence of any channel post or roll row; try
the write routes with the read token; close, and confirm the command reports no open conversation.

## Open questions

1. Whether `group` on these routes should be the group id or name - whichever `/api/rolls` already
   takes is the right answer; gm-assistant will send that.
2. Whether Discord command registration needs anything beyond what 211's deploy step already does.
