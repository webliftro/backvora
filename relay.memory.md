# relay.memory — shared cross-task lessons (relayflow)

> The relay's agents don't share memory; this committed file is the one place a durable lesson
> survives a handoff (Claude ↔ the cross-model Reviewer) — it travels via git, so both models read
> the same lessons. This is what makes the cross-model relay actually *share* what it learns.
>
> **Discipline — keep it short or it rots into noise no one reads:**
> - **One dated line per lesson** — append with `flow memory add "<lesson>"` (don't hand-format).
> - **Durable *cross-task* facts only** — a gotcha that should change how the NEXT task is built.
>   Per-task notes belong in that task's `STATE.md` baton, not here.
> - **Advisory, not gospel** — verify a lesson still holds before relying on it; a wrong line is
>   cheap to ignore. Prune stale lines by editing this file directly (humans prune; the tool appends).

