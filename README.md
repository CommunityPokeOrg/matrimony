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
  included), rendered as an inline text tree, plus `parent`, `children`,
  `siblings`, `familysize`, `relationship`.
- **Global trees** — like the original MarriageBot, family relationships are
  stored globally and follow users across every server the bot is in.
- **Custom prefixes** — per-guild prefix (`!matr prefix ?` → `?matr marry`).
- **Channel restrictions** — optional per-guild allow-lists confine
  commands to specific channels (`MATRIMONY_ALLOWED_CHANNELS`).
- **Incest toggle** — `!matr incest` lets server admins permit proposals
  between family members (off by default, as upstream).
- **Blocks** — users can `block`/`unblock` others from proposing to them.
- **Admin force commands** — `forcemarry`, `forcedivorce`, `forceadopt`,
  `forceemancipate` (Manage Server).
- **Fun commands** — `hug`, `cuddle`, `kiss`, `pat`, `poke`, `wave`,
  `lick`, `nom`, `tickle`, `highfive`, `handhold`, `slap`, `punch`,
  `bite`, `stab`, `ship`, `flirt` (terrible pickup lines), `date`
  (terrible date ideas), `anniversary` (how long you've been married),
  each with a random SFW anime GIF via the
  [Fluxpoint API](https://docs.fluxpoint.dev/api/endpoints/sfw-anime-gifs)
  (like the original MarriageBot).
- **Bot-directed quips** — aiming an action at Matrimony itself appends a
  rotating one-liner as Discord subtext (a `-# ` line) under the normal
  reply, and proposals at the bot are declined outright ("sorry, taken by
  discord.py").
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
  mention prefix, and whitespace after the prefix (`! matr help`) is
  accepted.
- Covered by tests: proposal/accept flows driven by bot-authored commands
  (`tests/test_dispatch.py`).

## Command reference

| Command | Description |
| --- | --- |
| `!matr help` | Show the command list |
| `!matr marry @user` | Propose to a user or bot (existing partners get an accept/divorce notice) |
| `!matr divorce [@user]` | Divorce a partner (required if you have several) |
| `!matr accept [@proposer]` / `decline` | Answer a pending proposal — `accept` also acknowledges partner notices |
| `!matr partners [@user]` | List partners |
| `!matr adopt @user` | Ask to adopt a user as your child |
| `!matr makeparent @user` | Ask a user to become your parent |
| `!matr disown @child` / `disownall` | Remove one/all children |
| `!matr emancipate` (alias `runaway`) | Remove your parent |
| `!matr abandon` | Remove all your family ties |
| `!matr tree [@user]` / `fulltree [@user]` | Blood / full family tree |
| `!matr parent` / `children` / `siblings` [@user] | Relatives at a glance |
| `!matr familysize [@user]` | Size of a user's tree |
| `!matr relationship @a @b` | How B relates to A |
| `!matr block` / `unblock @user` / `blocked` | Manage proposal blocks |
| `!matr prefix [new]` | View/set guild prefix (Manage Server) |
| `!matr incest` | Toggle incest proposals (Manage Server) |
| `!matr forcemarry @a @b` | Force-marry a pair (Manage Server) |
| `!matr forcedivorce @a [@b]` | Force-divorce (Manage Server) |
| `!matr forceadopt @parent @child` | Force adoption (Manage Server) |
| `!matr forceemancipate @user` | Force-remove a parent (Manage Server) |
| `!matr hug`/`cuddle`/`kiss`/`pat`/`poke`/`wave`/`lick`/`nom`/`tickle`/`highfive`/`handhold`/`slap`/`punch`/`bite`/`stab @user` | Flavour actions (+ GIF) |
| `!matr ship @a [@b]` | Deterministic ship percentage (+ GIF) |
| `!matr flirt @user` (alias `rizz`) | Terrible pickup line (+ GIF) |
| `!matr date @user` (alias `dateidea`) | Terrible date idea (+ GIF) |
| `!matr anniversary [@partner]` (alias `anniv`) | Time married (+ GIF) |
| `!matr info` / `invite` / `stats` | Bot information |

`@Matrimony matr ...` (mention prefix) also always works.

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

- Upstream renders trees as Graphviz images; Matrimony renders inline text
  trees (no Graphviz dependency, works in DMs and on lightweight hosts).
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
