# Built with Cursor

Cursor was used on this project from 22 Oct 2026. The owner confirms Cursor's agent worked on the repository.

What the screenshots show:

- `docs/cursor/cursor-agent-session.png`: Cursor's agent window, project `ledgerwise`, session "Hackathon project feedback". The conversation walks through the seeded demo day (the NGN 4.2M gap and its four causes with kobo amounts), the SQL guard rejecting a ticket that says `DELETE FROM processor.transactions`, the decision to keep Meterless in scope and not fake an endpoint, and the Zetaris REST client built from their public helper. The Zetaris API token that was visible on screen in the original screenshot has been cropped out.
- `docs/cursor/cursor-ide-ledgerwise.png`: the repository open in the Cursor IDE (`backend/app/main.py`), with the same agent session beside it. The agent reports it ran `./preflight.sh`, `docker compose pull` and `docker compose up -d` for the local Zetaris platform, and a session length of 10 h 6 m.

What was built where (as best this repo can tell):

- 22 Oct 2026, Cursor: reading the rules, the seeded data generator, the SQL guard and its tests, the local cross-source join, the Zetaris REST client, and standing up the local Zetaris platform.
- 27 Oct 2026: Zetaris source registration, the falsification step, the streaming agent, the FastAPI app and UI, the 21-scenario eval, the Nemotron and Meterless integration, and the demo video and deck were done in a separate Claude Code session, then pushed to this repository.

`.cursor/rules/ledgerwise.mdc` points Cursor at `CLAUDE.md` so Cursor sessions follow the project rules.
