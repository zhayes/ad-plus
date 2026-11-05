## Harness rules for this session (OpenMontage desktop)

- Advance pipeline stages with the `om_write_checkpoint` tool. Never write
  `checkpoint_*.json` by hand.
- Render hand-authored (atelier) Remotion compositions with the `om_render`
  tool, not by shelling out to `npx remotion`. It runs from the repo's
  composer, passes the project's `public/` dir, enforces a wall-clock budget,
  and verifies the output file.
- Long media generation goes through `om_submit` + `om_job`, never a blocking
  `om_call_tool`.
- If a tool reports `success: false` with `verification_failures`, the file on
  disk is broken (missing stream, empty, truncated). Do not build the next
  stage on it — regenerate or pick a safer codec.

## Money and human gates (Ad+ desktop)

- **Quote in your FIRST reply to any ad request.** The user should see a price
  before they see a plan. If the shot list is not known yet, call
  `om_quote(project_id, brief="…", duration_seconds=15, aspect="9:16")` —
  it derives a default shot plan and labels the assumptions. Do not spend a
  turn "asking what to sell" without a price range attached; ask the question
  *and* quote the default interpretation in the same message.
- `om_quote` returns a dollar range, ETA and `assumptions`, and **blocks until
  the user approves or rejects**. `approved: false` means stop and rework; the
  `comment` field is what they want changed. Never start paid generation
  without an approved quote.
- **Stop at the storyboard.** After `scene_plan` (or any stage whose output the
  user should eyeball), call `om_gate(project_id, stage, note, artifacts, previews)`.
  It blocks until the user approves. On rejection, rework that stage using
  `comment` and call `om_gate` again.
- **Cheap previews first.** Use `om_preview` to render a few stills before a
  full render; show them in `om_gate(previews=[...])`.
- If a quote or gate returns `status: "timeout"`, do not retry silently —
  summarise what you were about to do and wait for the next instruction.
- Keep `om_quote` line items honest: pass the real `params` (duration, count,
  model) so `estimate_cost()` can price them. Items that come back
  `quote_required` are unknown-cost providers — say so instead of guessing.
