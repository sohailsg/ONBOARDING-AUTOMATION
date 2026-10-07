# n8n + executor (05-impl)

- `workflows/intake.json` — Workflow A: HRIS webhook (HMAC) → validate →
  `POST /api/v1/onboarding/trigger` with `Idempotency-Key`, 3x backoff retry,
  DLQ to HR inbox. Import via API on deploy (git-import only, no manual edits).
- `mcp_tools/*.json` — idempotent tool defs (`send_email`, `post_slack`,
  `create_ticket`, `write_hris`, `create_notion_page`, `create_invite`).
- `mcp_servers.json` — task 5.1 decision log (Notion official, Google
  Workspace calendar — not `server-google-maps/calendar`).
- `field_mappings/` — Jira / BambooHR / email-template / Slack mappings +
  `SIGNOFF.md` (IT/HR sign-off sheet).

Deterministic executor: `backend/executor/` (`runner.py` + `tools/` wrappers).
`MCP_MODE=sandbox` until pilot sign-off (loopback tool URLs only).
