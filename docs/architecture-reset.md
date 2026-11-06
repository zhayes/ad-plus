# Ad+ architecture reset — OpenMontage-aligned

## Decision

Ad+ is the **commerce product layer**, not a second execution engine.

```text
Ad+ domain/UI
  projects / brief / quotes / review
  personas / products / brands
        ↓ thin adapter
OpenMontage
  pipeline manifests / checkpoint / gates
  ToolRegistry / video_selector
  canonical artifacts
        ↓
providers
```

No new Ad+ execution orchestrator. No direct tool imports in Ad+ execution
paths. No duplicate stage state that cannot be derived from canonical artifacts.

## Existing divergence to remove

| Ad+ today | Target |
|---|---|
| `adplus/digital_human.py` take state machine | `avatar-spokesperson` assets stage + tool registry |
| `adplus/capabilities.py` provider metadata | thin cache over ToolRegistry/profile metadata |
| `adplus/product_composite.py` private post-process | registered tool / compose step |
| `adplus/production.py` static 7-stage truth | derives from pipeline manifest + checkpoint/artifacts |
| `project_store` versions as source of truth | UI index over canonical artifacts + render |
| hardcoded `ROUTES` | route catalog from manifests + availability |

## Keep (real differentiation)

- persona library + consent/rights
- locked product library + label/SKU
- brand kit
- quote / approval / review UX
- commerce format presets
- product truth QA (label OCR)
- Ad+ stage board as a *view*, not a second pipeline

## Canonical target pipeline

Use `avatar-spokesperson` for presenter-led work:

```text
idea → script → scene_plan → assets → edit → compose → publish
```

For product/source footage, use `hybrid`; for pure motion graphics, `animation`.

A commerce "host product ad" is a **format preset** that selects one of these
pipelines, not a new pipeline unless the manifest genuinely needs new stages.

## Quality contract

1. **Presenter identity**: one persona, explicit rights, provider look/face id.
2. **Voice**: script → TTS/audio; lip sync is a required gate for close-up.
3. **Product truth**: locked product plate; model does not redraw SKU/label.
4. **Same-frame honesty**: do not claim host holds the real SKU unless real
   footage or a validated composite exists.
5. **QA gates**: label OCR, identity spotcheck, lip-sync acceptance, CTA.
6. **Benchmark**: same 10s brief across providers; compare identity, label,
   hands, lip sync, cost, latency.

## Phases

### P0 — Freeze and map (implemented)

- Add `pipeline_adapter.py` loading manifests.
- Route catalog derives pipeline/stages/artifacts from manifests.
- Digital-human execution resolves tools through `ToolRegistry`.
- Document boundary and remove direct imports from execution paths.

Implemented:
- `adplus/pipeline_adapter.py` reads upstream manifests.
- `production` payload exposes `pipeline`, `canonical_stage`, `canonical_artifact`.
- `digital_human` resolves tools through `ToolRegistry` (no direct avatar imports).
- `adplus/canonical_artifacts.py` + `POST /api/projects/{id}/canonical/sync` writes schema-valid `brief`, `script`, `scene_plan`, `asset_manifest`.
- `script_for` accepts canonical `sections`.

Acceptance:
- `production` payload reports canonical pipeline/stages/artifacts.
- Tests for adapter, payload and canonical artifacts.

### P0.5 — Request contract probes (implemented)

- `adplus/request_probe.py` builds sanitized provider request envelopes without sending them.
- Uses the same tool builders as execution (`seedance_ark`, `minimax_video`, `kling_avatar`, `heygen_avatar`, `lip_sync`).
- Checks endpoint/model/resolution/duration/reference blocks, and warns when a `cn` profile is pointed at a global endpoint.
- API: `POST /api/request-probe`.

This validates **request shape**, not visual quality. It is the right gate while keys are missing.

### P1 — One vertical slice

Implemented plumbing:
- `pipeline_runner.py` writes schema-valid checkpoints for `idea`, `script`, `scene_plan`, `assets`.
- `run_assets_stage()` plans/probes/optionally executes a digital-human take and writes `asset_manifest`.
- Ad+ stage board reads checkpoint status first, then falls back to legacy artifact state.
- API: `POST /api/projects/{id}/pipeline/bootstrap`, `POST /api/projects/{id}/pipeline/assets`.

Completed in P1 smoke:
- Real local Wav2Lip take, 6.57s, 480x720, h264/aac.
- `idea → script → scene_plan → assets → edit → compose → publish` checkpoints completed.
- `asset_manifest`, `edit_decisions`, `render_report`, `final_review`, `publish_log` written.
- Evidence: `docs/verification/p1-wav2lip-6s.mp4`, `docs/verification/p1-checkpoints.json`.
- Integration notes: `docs/wav2lip-integration.md`.

Still required for production:
- 9:16 480x854 output (current Wav2Lip smoke is 480x720).
- better lip-sync / identity / motion than Wav2Lip.
- Ad+ version points to the render in the app UI, not just a temp verification project.

Acceptance:
- 10s 480p output with a real lip-sync path (local or provider).
- Blocked providers surfaced before spending.

### P2 — Product truth (started)

- `adplus/oms_tools.py` registers `product_plate` in ToolRegistry.
- deterministic overlay, zero cost, label remains visible.
- `adplus/formats.py` + `/api/formats` provide `host_product_ad`, `ugc_testimonial`, `product_demo`.
- New-project dialog selects a format and carries route/pipeline.
- Routes are capability-driven (`hybrid`/`avatar_spokesperson` enable only when a provider is available).

Implemented:
- `pipeline_runner.complete_render(product_id=...)` invokes `product_plate` before compose.
- `POST /api/projects/{id}/pipeline/complete` exposes it.
- Product must be locked and AI-reference allowed; otherwise the compose is rejected.

Remaining: label QA gate on the final plate.


- Register product plate as a tool/compose step.
- Attach product to `asset_manifest` with `locked=true`.
- QA label OCR + manual review gate.

Acceptance:
- Real product visible; generated product is never presented as the SKU.

### P3 — Format presets / UI (started)

- `/api/formats`: `host_product_ad`, `ugc_testimonial`, `product_demo`.
- New-project dialog selects a format and carries route/pipeline/duration.
- Route availability is derived from capability status (Wav2Lip enables avatar route).

Remaining: remove the old Ad+ stage ownership and make the board checkpoint-only.


- `host_product_ad`, `ugc_testimonial`, `product_demo`.
- Stage board derives from canonical stages.
- Remove duplicate Ad+ stage logic.

## Non-goals

- Rebuilding a generic video editor.
- Replacing OpenMontage's EP/skills with Ad+ prompts.
- Supporting every model through custom Ad+ adapters.
- 5-minute ads before 10/15/30s are stable.
