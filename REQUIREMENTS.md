# Requirements

What the user wants from chrome-gateways (named agent-chrome until 2026-11-24), from the user's point of view only: **the benefit, never the mechanism**. How it is built is in [`DESIGN.md`](DESIGN.md). Words are used as defined in the vocabulary table of [`AGENTS.md`](AGENTS.md). Gathered 2026-11-23 from the user's review of everything the project did, revised 2026-11-24 into three gateways (the user: "1 entrypoint for agents"; "the links… is more a UX problem, not explaining how agents should use Chrome").

## Goal

My agents and my scripts browse a lot: scheduled jobs, scripts, interactive sessions, many subagents at once. I want that browsing to **never disrupt my work**, to be **traceable** (who opened what, when, for which project and why), and to **leave nothing behind**. When an agent browses, I want to see at a glance whether it is working alone or needs me, and to talk to it from the tab. Agents log in to sites without ever seeing a password. And every file or link an agent gives me is one click away, opening in the right Chrome profile.

Three gateways, one per kind of caller: **an agent browsing** (the agent gateway), **code opening pages** (the script gateway), **me clicking a link** (terminal links).

## Primary requirements

### The agent gateway: an agent browsing a page itself

| # | Requirement |
|---|---|
| R1 | **One way in for agents**: an agent that looks at a page itself always goes through the agent gateway; it never chooses between headless and visible. |
| R2 | **Visible, never in front.** I can watch an agent's tab if I want; it never jumps in front of what I am doing. |
| R3 | **One window per Claude account and desktop**, reused: an agent's tab joins the window of its Claude account's profile on its session's desktop, instead of piling up new windows. |
| R4 | **Never my own Chrome profile for an agent.** It holds my password vault. |
| R5 | **Always the Chrome profile of the session's Claude account**, simply. |
| R6 | **Logging in without seeing a password**, with my grant: agent-vault types logins into an agent's tab; this project tells it which session owns which tab. The two projects stay compatible, and their joint behaviour is tested. |
| R9 | **I see whether the agent needs me**: a tab shows whether the agent works alone or waits for me, and exactly what I must do. |
| R10 | **A tab waiting for me does not stay forever**: when nobody acts on it for a while, it closes and the agent is told. |
| R11 | **I can write to the agent from its tab**, and read its answer there. |
| R12 | **Many subagents, each with its own tab**: the tab shows its own subagent, and what I write on it reaches that subagent only. |

### The script gateway: code opening pages

| # | Requirement |
|---|---|
| R13 | **Code never shows me a window**: a script, a test or a scheduled job browses headless, on the Mac and on the NAS. |
| R19 | **Both machines**: the same on the NAS as on the Mac, recorded the same way. |

### Both gateways

| # | Requirement |
|---|---|
| R7 | **Every tab says who and why**: which Claude session (or scheduled job) opened it, when, for which project, why. Very important. |
| R8 | **Everything that opens is recorded**, including the tabs I close myself. Nothing opens Chrome without being recorded. |
| R14 | **Nothing left behind**: each agent closes what it opened, even when it fails; a killed script never leaves a Chrome running; a cleaning pass that I or a job can run closes, from the record, what nobody needs any more and lists the rest. It never closes a tab I opened. |
| R18 | **Which Chrome profile belongs to which Claude account is written in one place**, read by everything that needs it. |

### Terminal links: me clicking

| # | Requirement |
|---|---|
| R15 | **Every file or page an agent gives me is a full, clickable link**, as the Mac sees it: an agent on the NAS gives the path in the NAS's shared folder as mounted on the Mac; a NAS file outside them: an Artifact, or a copy put in a shared folder. Agents never open a window to show me something. |
| R16 | **A claude.ai link I click in a Claude session's terminal opens in that session's Claude account profile** (an Artifact is shown only to that account). Any other link or page opens in my own Chrome profile; any other file as macOS opens it. |

## Secondary requirements (nice to have, later)

| # | Requirement |
|---|---|
| R20 | **My message reaches an idle or ended session.** What I write on a tab wakes the agent that opened it, or tells me how to resume its session. Without it R11 is of little use (4 messages written from tabs, 1–23 Nov 2026). |

## Out of scope

- **A list of the sites an agent may open**, here or in any project (removed from jobs on 2026-11-23, commit `2834ea5`).
- **An agent choosing headless or visible**, or switching a tab between them (2026-11-24): agents are visible, code is headless.
- **A headless Chrome with a second login to one of my real accounts**: a new login from an unknown browser looks like a bot and risks the account (2026-11-23).
- **agent-vault for code**: no agent is in the loop to protect; code logs in with its own data folder or its own secrets file (2026-11-24).
- **Alerts and notifications to me**: each agent decides whether to alert me (1 Nov 2026); this project only shows the facts on the tab.

## Decided questions

| Question | Answer (date) |
|---|---|
| How many ways into Chrome? | Two, one per kind of caller: agents (Claude in Chrome) and code (headless); plus my clicks (2026-11-24) |
| Headless or visible? | An agent browsing: visible, never in front. Code: headless. Nobody chooses (2026-11-24; replaces "the agent decides", 2026-11-23) |
| Sites logged in with my real accounts (LinkedIn…)? | Through the agent gateway, in the real profile, never in front: a headless second login risks a ban (2026-11-23) |
| One window per project, or per account? | Per Claude account and desktop (2026-11-23; replaces "per project" of 1 Nov 2026) |
| Which profile? | Always the session's Claude account's; never mine (2026-11-23) |
| Which profile for a link I click? | A claude.ai link in a Claude session's terminal: that session's account profile. Anything else: my own profile (2026-11-24; replaces "the session's profile for every link", 2026-11-23) |
| An agent showing me a page? | It gives the link; I click it. No window opened by an agent (2026-11-24) |
| The NAS seen from the Mac? | Its shared folders as mounted on the Mac: `/Volumes/public/` or `/Volumes/private/` (2026-11-23) |
| A NAS file outside the shared folders? | An Artifact or a copy in `/public` or `/private` for now (2026-11-23) |
| Keep the subagents mode? | Yes, very important, with the tab extension working in it (2026-11-23) |
| Keep writing to the agent from the tab without R20? | Yes, for now (2026-11-23) |
| Separate profiles, or one shared? | Separate: one per Claude account (2026-11-21) |
| The project's name and layout? | chrome-gateways, three folders: agent-gateway, script-gateway, terminal-links (+ shared) (2026-11-24) |
