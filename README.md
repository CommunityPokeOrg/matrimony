# Matrimony

A MarriageBot-style family-tree bot for Discord, written in Python with
[discord.py](https://github.com/Rapptz/discord.py). Users can marry, divorce,
adopt, disown, and render family trees — **for humans and bot accounts alike**.

All commands live under one group, `matr`, invoked with a per-guild prefix
(default `!`) or as Discord slash commands:

```
!matr <action> <params>
/matr <action> <params>
```

## Features

- **Marriages** — propose, accept/decline (buttons *or* text commands),
  divorce, multiple simultaneous partners. When a married user takes
  another partner, every existing partner (of *both* spouses) is notified
  and can **accept** (acknowledge the arrangement) or **divorce** on the
  spot — the new marriage stands either way.
- **Parentage** — `adopt` (they become your child) and `makeparent` (they
  become your parent), `disown`, `disownall`, `emancipate`/`runaway`,
  `abandon` (wipe your whole family).
- **Family trees** — `tree` (blood relatives) and `fulltree` (partners
  included), posted as a PNG image with member avatars (rendered from a
  self-contained SVG via cairosvg, so Discord inlines it), plus
  `parent`, `children`, `siblings`, `familysize`, `relationship`. Pass
  `text` to get the plain inline listing instead, or to fall back when
  image rendering fails.
- **Global trees** — like the original MarriageBot, family relationships are
  stored globally and follow users across every server the bot is in.
- **Custom prefixes** — per-guild prefix (`!matr prefix ?` → `?matr marry`).
- **Channel restrictions** — optional per-guild allow-lists confine
  commands to specific channels (`MATRIMONY_ALLOWED_CHANNELS`).
- **Incest toggle** — `!matr incest` lets server admins permit proposals
  between family members (off by default, as upstream).
- **Blocks** — users can `block`/`unblock` others from proposing to them.
- **Restraining orders** — `restrain` blocks every targeted action a user
  aims at you for one hour; a violation prompts you to press charges,
  which sends the offender to jail.
- **Jail** — inmates can't act on free users, but can marry, adopt, and
  interact with each other in ephemeral jail-only relationships that
  dissolve the moment the sentence ends.
- **Admin force commands** — `forcemarry`, `forcedivorce`, `forceadopt`,
  `forceemancipate` (Manage Server).
- **Guild reset** — `clear` wipes this server's settings, proposals,
  notices, restraining orders, and jail sentences behind a confirmation
  prompt (Manage Server).
- **Fun commands** — `hug`, `cuddle`, `kiss`, `pat`, `poke`, `wave`,
  `lick`, `nom`, `tickle`, `highfive`, `handhold`, `slap`, `punch`,
  `bite`, `stab`, `ship`, `flirt` (terrible pickup lines), `date`
  (terrible date ideas), `anniversary` (how long you've been married),
  each with a random SFW anime GIF via the
  [Fluxpoint API](https://docs.fluxpoint.dev/api/endpoints/sfw-anime-gifs)
  (like the original MarriageBot).
- **Drifting ship percentages** — `ship @a @b` is deterministic for a
  pair at a given moment, but wanders smoothly over ~24h instead of being
  pinned forever, and busy channels nudge it: the score includes the
  rolling count of channel messages over the last 10 minutes (a small,
  bounded in-memory window fed by every observed message, bots included).
- **Ambient quips everywhere** — basically every command reply ends with
  one rotating one-liner of commentary, rendered as Discord subtext (a
  `-# ` line) at the bottom of the embed or message. All quips live in a
  single file (`matrimony/quips.py`) organized by command and theme:
  marriage, divorce, trees, blocks, law, admin, fun actions, meta, and
  more.
- **Bot-directed quips** — aiming an action at Matrimony itself swaps the
  ambient line for one from the bot's own pool, and proposals at the bot
  are declined outright ("sorry, taken by discord.py").
- **Unknown-action quips** — `!matr blorp` (or any nonexistent action)
  gets a rotating funny quip as subtext plus the help embed, never
  silence. The bot's own messages never trigger it.
- **Marital wisdom** — `!matr help` (and bare `!matr`) ends with one
  randomly chosen quip about memes, Discord culture, programming, and
  relationships, rendered as Discord subtext below the full command
  listing.
- **Slash commands** — every command is a discord.py hybrid, so `/matr`
  mirrors `!matr` exactly: `/matr marry`, `/matr fun hug`,
  `/matr admin forcemarry`, `/matr meta stats`.
- **Meta** — `info`, `invite`, `stats`, `help`.

## Bot accounts are first-class

Unlike upstream MarriageBot (which refuses to let bots take part), Matrimony
explicitly supports bot-authored commands and bot targets:

- Humans can marry/adopt bots, bots can marry/adopt humans, and bots can
  marry/adopt each other.
- The message listener does **not** ignore `message.author.bot`; other bots'
  command messages are dispatched exactly like human ones. (This requires
  overriding `process_commands`: discord.py drops all bot-authored
  messages in its default dispatch.)
- The only exclusion is Matrimony's *own* messages — enough to prevent
  self-command loops while leaving every other bot free to participate.
- Command parsing is lenient: leading/trailing whitespace and extra text
  after the arguments are tolerated, `@Matrimony matr ...` works as a
  mention prefix, whitespace after the prefix (`! matr help`) is
  accepted, and the command may sit on **any line** of the message —
  chatter first, then `!matr <action>` on its own line, still runs.
- Covered by tests: proposal/accept flows driven by bot-authored commands
  (`tests/test_dispatch.py`).

## Command reference

| Command | Description |
| --- | --- |
| `!matr help [bot]` | Show the command list; `help bot` shows bot-specific guidance |
| `!matr marry @user` | Propose to a user or bot (existing partners get an accept/divorce notice) |
| `!matr divorce [@user]` | Divorce a partner (required if you have several) |
| `!matr accept [@proposer]` / `decline` | Answer a pending proposal — `accept` also acknowledges partner notices |
| `!matr partners [@user]` | List partners |
| `!matr adopt @user` | Ask to adopt a user as your child |
| `!matr makeparent @user` | Ask a user to become your parent |
| `!matr disown @child` / `disownall` | Remove one/all children |
| `!matr emancipate` (alias `runaway`) | Remove your parent |
| `!matr abandon` | Remove all your family ties |
| `!matr tree [@user] [display]` / `fulltree [@user] [display]` | Blood / full family tree as an image (default) or `text` |
| `!matr parent` / `children` / `siblings` [@user] | Relatives at a glance |
| `!matr familysize [@user]` | Size of a user's tree |
| `!matr relationship @a @b` | How B relates to A |
| `!matr block` / `unblock @user` / `blocked` | Manage proposal blocks |
| `!matr restrain @user` | File a 1-hour restraining order against a user |
| `!matr prefix [new]` | View/set guild prefix (Manage Server) |
| `!matr incest` | Toggle incest proposals (Manage Server) |
| `!matr forcemarry @a @b` | Force-marry a pair (Manage Server) |
| `!matr forcedivorce @a [@b]` | Force-divorce (Manage Server) |
| `!matr forceadopt @parent @child` | Force adoption (Manage Server) |
| `!matr forceemancipate @user` | Force-remove a parent (Manage Server) |
| `!matr clear` | Reset this guild's state after a Confirm/Cancel prompt (Manage Server) |
| `!matr hug`/`cuddle`/`kiss`/`pat`/`poke`/`wave`/`lick`/`nom`/`tickle`/`highfive`/`handhold`/`slap`/`punch`/`bite`/`stab @user` | Flavour actions (+ GIF) |
| `!matr ship @a [@b]` | Drifting ship percentage (pair + time + channel chatter; + GIF) |
| `!matr flirt @user` (alias `rizz`) | Terrible pickup line (+ GIF) |
| `!matr date @user` (alias `dateidea`) | Terrible date idea (+ GIF) |
| `!matr anniversary [@partner]` (alias `anniv`) | Time married (+ GIF) |
| `!matr info` / `invite` / `stats` | Bot information |

`@Matrimony matr ...` (mention prefix) also always works, and the
command doesn't have to open the message — any line that starts with
the prefix is parsed as the command (everything else is chatter).

On the slash side, `restrain` is `/matr restrain` and `clear` lives under
the admin subgroup as `/matr admin clear`; `anniversary` is under
`/matr fun anniversary`.

## Restraining orders and jail

`!matr restrain @user` files a restraining order: for the next hour
(`MATRIMONY_RESTRAINING_ORDER_TTL`, default 3600s) every targeted action
the restrained user aims at the protected one is blocked — proposals
(`marry`, `adopt`, `makeparent`) and all targeted flavour actions (`hug`,
`slap`, `poke`, `punch`, `stab`, `flirt`, `date`, ...). `ship` is exempt
since it only reports a number. Refiling renews the hour. Enforcement
lives in the shared command entry point, so prefix and slash invocations
are blocked identically.

A violation posts a **Press charges / Let it slide** button prompt
(addressed to the protected user only, 120s timeout). Pressing charges
sends the offender to jail; declining or letting it lapse leaves the
restraining order standing until it expires.

**Sentencing scales by severity.** Light interactions are minor and roll
a random 1-5 minutes; serious actions have fixed sentences:

| Action | Sentence |
| --- | --- |
| light fun (poke, hug, cuddle, kiss, pat, wave, lick, nom, tickle, highfive, handhold, flirt, date) | random 1-5 min |
| slap | 10 min |
| adopt / makeparent | 15 min |
| bite / punch | 20 min |
| stab | 25 min |
| marry | 30 min |
| any unlisted action | 15 min (default major) |

**While jailed**, any targeted action aimed at a non-jailed user is
blocked with an error embed and a rotating quip — this covers proposals
*and* `divorce`, `disown`, and `block` attempts on free users. Inmates
can still `marry`, `adopt`, `makeparent`, and use fun actions on **other
inmates**; those proposals are flagged and create **jail relationships**
stored in separate `jail_partners`/`jail_children` tables, never in the
real family tree.

**Jail relationships are ephemeral.** When a sentence ends, the inmate is
released, every jail marriage and jail adoption they were part of is
dissolved, and both parties are told they were divorced or abandoned on
release — nothing carries over to the real tree.

A background sweep (`MATRIMONY_JAIL_SWEEP`, every 20s by default) expires
restraining orders (announced where they were filed), releases inmates,
and posts release + dissolution notices. The expiry core is a pure
function of the store and a clock (`jail.sweep_expiry`), unit-tested with
an injected clock.

## Resetting a guild

`!matr clear` (slash: `/matr admin clear`) is restricted to users with
**Manage Server** and never acts immediately: it shows a warning embed
listing the scope with **Confirm reset** / **Cancel** buttons (60s
timeout, invoking admin only; timeout or Cancel changes nothing).

On confirm it deletes, for that guild only, and replies with counts:

- guild settings (custom prefix, incest flag)
- pending proposals and partner notices filed in the guild
- restraining orders filed in the guild
- jail sentences handed down in the guild — inmates are released and
  their jail relationships dissolved

It does **not** clear partners, children, or block lists: the family tree
and personal blocks are global across servers, not guild state, so wiping
them would erase other guilds' data — the narrowest reading of "reset
this guild".

## Running

### Requirements

- Python 3.10+
- A Discord application + bot token (<https://discord.com/developers/applications>)
- Privileged **Message Content** and **Server Members** intents enabled in the
  developer portal (required for prefix commands and member lookups)

### Local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in MATRIMONY_TOKEN
export $(grep -v '^#' .env | xargs)
python -m matrimony
```

### Docker

```bash
docker build -t matrimony .
docker run -e MATRIMONY_TOKEN=... -v matrimony-data:/data matrimony
```

### Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `MATRIMONY_TOKEN` | *(required)* | Discord bot token |
| `MATRIMONY_DEFAULT_PREFIX` | `!` | Fallback prefix for guilds/DMs |
| `MATRIMONY_COMMAND_NAME` | `matr` | The command group name (`!matr` and `/matr`) |
| `MATRIMONY_DB_PATH` | `matrimony.db` | SQLite database file |
| `MATRIMONY_MAX_PARTNERS` | `0` | Partner cap per user (0 = unlimited) |
| `MATRIMONY_MAX_CHILDREN` | `0` | Children cap per user (0 = unlimited) |
| `MATRIMONY_MAX_TREE_DEPTH` | `10` | Depth limit when rendering trees |
| `MATRIMONY_PROPOSAL_TTL` | `300` | Seconds before a proposal expires |
| `MATRIMONY_ALLOWED_CHANNELS` | *(unset)* | JSON object mapping guild ids to lists of allowed channel ids (see below) |
| `MATRIMONY_ALLOWED_CHANNELS_FILE` | *(unset)* | Path to a JSON file with the same mapping; used when `MATRIMONY_ALLOWED_CHANNELS` is unset |
| `MATRIMONY_RESTRAINING_ORDER_TTL` | `3600` | Seconds a restraining order lasts |
| `MATRIMONY_JAIL_SWEEP` | `20` | Seconds between expiry sweeps (order expiry, jail release) |
| `FLUXPOINT_API_KEY` | Fluxpoint's shared public key | Fluxpoint API token for action GIFs; set to empty to disable |

### Channel restrictions

`MATRIMONY_ALLOWED_CHANNELS` takes a JSON object that maps a guild id to
the list of channel ids where commands are accepted:

```bash
MATRIMONY_ALLOWED_CHANNELS='{"123456789012345678": ["111222333444555666", "777888999000111222"]}'
```

A guild absent from the mapping is unrestricted (existing deployments are
unaffected). A guild mapped to an empty list (`"123": []`) accepts commands
in no channel. Commands used outside the allowed channels are **silently
ignored** — the message is never dispatched, matching how the bot already
ignores its own messages. DMs are never restricted. Threads are their own
channels: add the thread's id if commands should work there.

For larger setups, put the same JSON object in a file and point
`MATRIMONY_ALLOWED_CHANNELS_FILE` at it (the inline variable wins when
both are set). A malformed value logs a warning and is treated as no
restriction, so a typo can't lock every server out of the bot.

## Action GIFs

Action replies embed a random SFW anime GIF fetched from the Fluxpoint API
(`GET https://api.fluxpoint.dev/sfw/gif/<type>`, token in the `Authorization`
header). Mappings:

| Command | Fluxpoint endpoint |
| --- | --- |
| `marry` (marriage completed) | `kiss` |
| `divorce` | `cry` |
| `hug` | `hug` |
| `cuddle` | `hug` *(no `cuddle` endpoint exists; closest fit)* |
| `kiss` | `kiss` |
| `pat` | `pat` |
| `poke` | `poke` |
| `wave` | `wave` |
| `lick` | `lick` |
| `nom` | `feed` *(no `nom` endpoint exists; closest fit)* |
| `tickle` | `tickle` |
| `highfive` | `highfive` |
| `handhold` | `handhold` |
| `slap` | `slap` |
| `punch` | `punch` |
| `bite` | `bite` |
| `stab` | `punch` *(no `stab` endpoint exists; closest fit)* |
| `ship` | `handhold` |
| `flirt` | `wink` |
| `date` | `hug` |
| `anniversary` | `kiss` |

GIF fetching never blocks the action: a missing/empty key, HTTP error,
timeout, or malformed response just sends the reply without an image.

## Fidelity to the original MarriageBot

Matrimony replicates the original's mechanics as closely as is practical
(sources below):

- Same command surface: marry/divorce/partners, adopt/makeparent/disown/
  disownall/emancipate/runaway/abandon, tree/fulltree/parent/children/
  siblings/familysize/relationship, block/unblock, incest toggle, force
  commands, fun commands, info/invite/stats.
- **Cross-server global family trees.**
- **One parent per child**, matching upstream's single-parent tree model.
- Proposals need the target's consent (upstream uses buttons; Matrimony
  supports buttons *and* `accept`/`decline` text commands, which also lets
  non-UI bots respond). The marriage forms the moment the target accepts —
  existing partners of either spouse are then notified and may acknowledge
  or immediately divorce their own partner.
- `incest` is a per-guild admin toggle, off by default.
- No partner limit by default (upstream allows polygamy; caps are
  configurable here).

**Known divergences:**

- Upstream has no equivalent of Matrimony's partner notices: when a user
  marries someone new, each existing partner of both spouses gets an
  accept/divorce prompt (buttons or `accept`/`divorce` text commands).
  Accepting is purely an acknowledgement; it never blocks the marriage.

- Upstream renders trees as Graphviz images; Matrimony builds a
  self-contained SVG and rasterizes it to PNG (no Graphviz dependency,
  avatars inlined as data URIs), falling back to an inline text tree on
  request or on failure.
- Upstream has no documented "bots can be married" support — Matrimony adds
  it deliberately.
- Upstream now primarily uses slash commands; Matrimony supports both
  `!matr <action>` prefix commands (plus mention-prefix) and equivalent
  `/matr` slash commands via discord.py hybrid commands.
- Gold-tier/perks features (custom colours, bigger limits) are not
  replicated; limits are plain env vars instead.
- Slash-command-only upstream additions (`customize-tree`, `transfer-gold`,
  `runaway` alias kept as `emancipate` alias) are out of scope.
- Upstream sources GIFs from its own store; Matrimony uses Fluxpoint's SFW
  anime GIF API (provider's public-tier key by default, override via
  `FLUXPOINT_API_KEY`).

**Sources:**

- [Voxel-Fox-Ltd/MarriageBot](https://github.com/Voxel-Fox-Ltd/MarriageBot) —
  original bot source (Python, "cross-server family trees", command list).
- [top.gg command listing](https://top.gg/bot/468281173072805889/commands)
  and [alternative.me command listing](https://alternative.me/discord/bots/marriagebot/commands) —
  upstream command descriptions including `incest`, `disownall`, `abandon`,
  `makeparent`, and force commands.
- [docs.marriagebot.xyz](https://docs.marriagebot.xyz/) — upstream docs.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests   # unit tests (no Discord connection needed)
ruff check .             # lint
```

Storage is SQLite (`matrimony/store.py`); family-graph logic
(`matrimony/family.py`) is Discord-free and fully unit-tested. CI runs lint +
tests on Python 3.11/3.12.

## License

MIT — see [LICENSE](LICENSE).
