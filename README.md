# Matrimony

A MarriageBot-style family-tree bot for Discord, written in Python with
[discord.py](https://github.com/Rapptz/discord.py). Users can marry, divorce,
adopt, disown, and render family trees — **for humans and bot accounts alike**.

All commands live under one group, `matr`, invoked with a per-guild prefix
(default `!`):

```
!matr <action> <params>
```

## Features

- **Marriages** — propose, accept/decline (buttons *or* text commands),
  divorce, multiple simultaneous partners.
- **Parentage** — `adopt` (they become your child) and `makeparent` (they
  become your parent), `disown`, `disownall`, `emancipate`/`runaway`,
  `abandon` (wipe your whole family).
- **Family trees** — `tree` (blood relatives) and `fulltree` (partners
  included), rendered as an inline text tree, plus `parent`, `children`,
  `siblings`, `familysize`, `relationship`.
- **Global trees** — like the original MarriageBot, family relationships are
  stored globally and follow users across every server the bot is in.
- **Custom prefixes** — per-guild prefix (`!matr prefix ?` → `?matr marry`).
- **Incest toggle** — `!matr incest` lets server admins permit proposals
  between family members (off by default, as upstream).
- **Blocks** — users can `block`/`unblock` others from proposing to them.
- **Admin force commands** — `forcemarry`, `forcedivorce`, `forceadopt`,
  `forceemancipate` (Manage Server).
- **Fun commands** — `hug`, `kiss`, `slap`, `punch`, `bite`, `stab`, `ship`.
- **Meta** — `info`, `invite`, `stats`, `help`.

## Bot accounts are first-class

Unlike upstream MarriageBot (which refuses to let bots take part), Matrimony
explicitly supports bot-authored commands and bot targets:

- Humans can marry/adopt bots, bots can marry/adopt humans, and bots can
  marry/adopt each other.
- The message listener does **not** ignore `message.author.bot`; other bots'
  command messages are dispatched exactly like human ones.
- The only exclusion is Matrimony's *own* messages — enough to prevent
  self-command loops while leaving every other bot free to participate.
- Covered by tests: proposal/accept flows driven by bot-authored commands
  (`tests/test_dispatch.py`).

## Command reference

| Command | Description |
| --- | --- |
| `!matr help` | Show the command list |
| `!matr marry @user` | Propose to a user or bot |
| `!matr divorce [@user]` | Divorce a partner (required if you have several) |
| `!matr accept [@proposer]` / `decline` | Answer a pending proposal |
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
| `!matr hug`/`kiss`/`slap`/`punch`/`bite`/`stab @user` | Flavour actions |
| `!matr ship @a [@b]` | Deterministic ship percentage |
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
| `MATRIMONY_COMMAND_NAME` | `matr` | The command group name (`!matr ...`) |
| `MATRIMONY_DB_PATH` | `matrimony.db` | SQLite database file |
| `MATRIMONY_MAX_PARTNERS` | `0` | Partner cap per user (0 = unlimited) |
| `MATRIMONY_MAX_CHILDREN` | `0` | Children cap per user (0 = unlimited) |
| `MATRIMONY_MAX_TREE_DEPTH` | `10` | Depth limit when rendering trees |
| `MATRIMONY_PROPOSAL_TTL` | `300` | Seconds before a proposal expires |

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
  non-UI bots respond).
- `incest` is a per-guild admin toggle, off by default.
- No partner limit by default (upstream allows polygamy; caps are
  configurable here).

**Known divergences:**

- Upstream renders trees as Graphviz images; Matrimony renders inline text
  trees (no Graphviz dependency, works in DMs and on lightweight hosts).
- Upstream has no documented "bots can be married" support — Matrimony adds
  it deliberately.
- Upstream now primarily uses slash commands; Matrimony uses the requested
  `!matr <action>` prefix-command surface (plus mention-prefix support).
- Gold-tier/perks features (custom colours, bigger limits) are not
  replicated; limits are plain env vars instead.
- Slash-command-only upstream additions (`customize-tree`, `transfer-gold`,
  `runaway` alias kept as `emancipate` alias) are out of scope.

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
