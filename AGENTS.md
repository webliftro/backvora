
<!-- relayflow -->
## relayflow — task relay
This repo uses relayflow. When the user says a trigger phrase, run the matching role via the
`flow` CLI and follow its instructions exactly (don't ask for further instructions):
- **check the spec** → run `flow role spec-checker` (cross-model SPEC QA before the Builder; optional)
- **build the task** / **build next task** / **fix the task** → run `flow role builder`
- **review the task** → run `flow role reviewer` (you are the cross-model Reviewer; review only)
- **write the spec** / **spec the task** → run `flow role architect` (straight to the spec; skips the orchestrator's co-design gate)
- **verify the task** → run `flow role verifier` (the post-integration reality-check on the live deploy)
- **groom the relay** → run `flow role groomer` (distill the journal + batons into a ranked improvement digest; report-only)

**Default (no trigger phrase):** you are the **orchestrator** — the human's home session that drives a raw issue through recon → co-design → spec → dispatch → integrate. Run `flow role orchestrator` for your manual. Any worker trigger above wins, so a session given one is unaffected.

The role self-resolves the active task via `flow task <role>` — the one whose `docs/tasks/*/STATE.md`
baton has `Current owner = <role>`. The task's `SPEC.md` is the contract.
<!-- /relayflow -->
