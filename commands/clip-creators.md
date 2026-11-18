---
description: See and update the creator watchlist and who has given permission to be clipped.
argument-hint: [@handle granted|asked|denied|blocked|unknown] [notes]
---

`$ARGUMENTS` empty → show `list_creators()` as a table grouped by permission, and remind the user:
credit is not permission; ask creators directly ("Love this clip, ok if we share it with credit?").
With arguments → `upsert_creator(handle, permission=..., notes=...)` and show the result. Only set
`granted` when the user says the creator agreed.
