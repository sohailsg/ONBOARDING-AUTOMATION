# Field mappings sign-off (05-impl, task 5.5)

IT/HR sign-off sheet for Jira / BambooHR / email-template / Slack mappings.
All values point at **sandbox** workspaces until the pilot sign-off row is signed.

| Mapping | File | Owner | Status | Signed |
|---|---|---|---|---|
| Jira project / issue-type (`ONB-SANDBOX` / `Task`) | `n8n/field_mappings/jira.json` | IT | pending review | [ ] |
| BambooHR employee fields | `n8n/field_mappings/bamboohr.json` | IT | pending review | [ ] |
| Email templates (welcome, IT provisioning) | `n8n/field_mappings/email_templates.json` | HR | pending review | [ ] |
| Slack channels (`#*-sandbox`) | `n8n/field_mappings/slack_channels.json` | HR | pending review | [ ] |
| Pilot promotion (real project/channels, still behind approval) | — | IT + HR | blocked on sandbox e2e | [ ] |

Rule: new/changed tool or template → wrapper PR + sandbox e2e + sign-off here.
No direct n8n edits on shared instances (git-import only).
