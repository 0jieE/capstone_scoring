# Agent Prompt — Capstone Defense Scoring System (LAN-based)

You are building a working Django application inside this existing scaffold. Every stub file says
`TO BE IMPLEMENTED` and points to a section of this prompt. Implement them, keep the file layout,
and do not add frameworks beyond what is listed.

---

## 1. Context

The IT Education Department of Colegio de Kidapawan, Inc. holds capstone final defenses. Three people
score each group on a paper form:

- Examiner 1
- Examiner 2
- Research Coordinator

Totalling the paper forms by hand is slow and error-prone. Your job is to build a system where:

- the three panelists score from **different workstations on the same LAN**;
- the system **computes everything automatically**;
- once all three have submitted, it outputs the verdict: **PASSED, PASSED with MINOR REVISIONS,
  PASSED with MAJOR REVISIONS, or FAILED**.

The rubric is in `docs/rubric.md`. It is a transcription of the paper form; treat it as the source of truth.

## 2. Tech constraints

- **Python 3.11+, Django 5.x, SQLite.** Nothing else server-side. `requirements.txt` is just Django.
- **LAN and offline.** The venue may have no internet, so:
  - use no CDN links and no external fonts;
  - put all CSS and JS in `static/`;
  - write plain, vanilla JS only.
- **Server.** The host runs `python run_lan.py`, which binds `0.0.0.0:8000` and prints the URL panelists
  should open (`http://<LAN-IP>:8000`). `ALLOWED_HOSTS = ["*"]` is already set.
- **SQLite and concurrent saves.** The `timeout` option is already set. Keep each save in a short
  `transaction.atomic()` block.
- **Money-style math.** Use `Decimal` for every score; floats are not allowed.
- **Settings.** `capstone_scoring/settings.py` is already configured: timezone Asia/Manila, a context
  processor exposing `INSTITUTION`, and login URLs. Keep it.

## 3. Users and roles

Use Django auth. Each panelist is an auth `User` with a `Panelist` profile.

| Role | Who | Can do |
|---|---|---|
| Manager (`is_staff=True`) | Research Coordinator or admin | Everything below, plus: create/edit defenses, proponents and panel assignments; manage panelist accounts; change scoring settings; open/close a defense; unlock a submitted evaluation; view all results. |
| Panelist | Any assigned examiner or coordinator | See only the defenses they are assigned to; fill in and submit their own evaluation; view results of their defenses once all 3 have submitted. |

A manager can also be assigned as a panelist (the Research Coordinator usually is both).

## 4. Scoring rules (implement in `defense/scoring.py` only)

### Definitions
- **r** is a rating from 1 to 5.
- **w** is a criterion weight written as a fraction (20% is 0.20).
- The weighted score of a criterion is **r × w**.

### Per panelist (matches the paper form)

**Section scores**
- **A** (System, 45%) = sum of r × w for criteria 1, 2 and 3. These are rated once for the whole group.
- **B** (Manuscript, 20%) = r × w for criterion 4. Rated once for the whole group.
- **C** (Oral Defense, 35%) = sum of r × w for criteria 5 and 6. These are rated **separately for each
  proponent**, so each proponent has their own C.

**Final scores**
- **FINAL for a proponent** = A + B + that proponent's C.
- **Group FINAL** = A + B + the average C across all proponents. This mirrors the single C value
  panelists wrote on paper.

### Consolidated score (all 3 submitted)

Let **W** be a panelist's weight. The defaults are Examiner 1 = 35, Examiner 2 = 35, Research
Coordinator = 30. The values are stored on each `PanelAssignment` so that changing settings later never
alters past results.

```
consolidated = Σ (panelist FINAL × W) / Σ W
```

Compute this for:
- each proponent's FINAL;
- the group FINAL;
- A, B and C separately, for the breakdown display.

### Rounding and verdict

- Round the consolidated score to 2 decimals using ROUND_HALF_UP.
- Apply the verdict to that rounded value.
- Cutoffs are stored in `ScoringSettings` and are editable. Use **≥** comparisons:

| Score | Verdict |
|---|---|
| ≥ 4.50 | PASSED |
| ≥ 3.50 | PASSED with MINOR REVISIONS |
| ≥ 2.50 | PASSED with MAJOR REVISIONS |
| below 2.50 | FAILED |

The paper form's bands have gaps (4.4–4.5 and 3.4–3.5). The cutoffs above close those gaps.

### Who gets a verdict

- Each proponent gets **their own consolidated score and verdict**.
- The group also gets one, shown as the headline.
- Show nothing as final until all 3 evaluations are submitted. Before that, show each panelist's
  status (Not started / Draft / Submitted).

### Worked example (must pass as a test)

One panelist, two proponents, both rated 5 on criterion 5 and 4 on criterion 6:

| Criterion | Weight | Rating | r × w |
|---|---|---|---|
| 1 | 0.20 | 4 | 0.80 |
| 2 | 0.15 | 5 | 0.75 |
| 3 | 0.10 | 4 | 0.40 |
| 4 | 0.20 | 4 | 0.80 |
| 5 | 0.15 | 5 | 0.75 |
| 6 | 0.20 | 4 | 0.80 |

Result: A = 1.95, B = 0.80, C = 1.55, FINAL = 4.30 → PASSED with MINOR REVISIONS.

If all 3 panelists give exactly these ratings, the consolidated score is also 4.30.

## 5. Data model (`defense/models.py`)

Implement these models.

**`ScoringSettings`** (single row; `load()` classmethod)
- `examiner1_weight`, `examiner2_weight`, `coordinator_weight` (Decimal, percent, default 35/35/30)
- `passed_cutoff` 4.50, `minor_cutoff` 3.50, `major_cutoff` 2.50

**`Criterion`**
- `number` (unique, 1–6), `section` (A/B/C), `name`, `guide_question`
- `weight` (Decimal fraction), `per_proponent` (bool)
- `desc_5` … `desc_1` (descriptor text), `is_active`

**`Panelist`**
- OneToOne to `User`
- `prefix` (Engr., Dr.), `suffix` (LPT, CCpE)
- `display_name` property, e.g. "Engr. Jelmar L. Villaruel, LPT"

**`Defense`**
- `title`, `schedule_date`, `schedule_time`, `venue`
- `status` (open/closed), `created_at`

**`Proponent`**
- FK `Defense`, `full_name`, `order`

**`PanelAssignment`**
- FK `Defense`, FK `Panelist`, `role` (EX1 / EX2 / RC), `weight` (percent)
- Unique on (defense, role) and on (defense, panelist)

**`Evaluation`**
- OneToOne `PanelAssignment`
- `comments` ("Required Revisions / Comments")
- `submitted`, `submitted_at`, `updated_at`

**`GroupRating`**
- `evaluation`, `criterion`, `rating` (1–5)
- Unique on (evaluation, criterion)

**`IndividualRating`**
- `evaluation`, `criterion`, `proponent`, `rating` (1–5)
- Unique on (evaluation, criterion, proponent)

**Rubric seeding.** Seed the rubric from `docs/rubric.md` with a data migration (or with
`seed_rubric`, and call it from the migration) so a fresh `migrate` always has the 6 criteria.

## 6. Pages and features

Use offline CSS. Keep the look clean and printable. It must be usable on a laptop and on a phone.

**1. Login**
- Uses `templates/registration/login.html`.

**2. Dashboard**
- Lists defenses with title, schedule, proponents, and a status chip (e.g. `2/3 submitted`).
- Panelists see only their own defenses, each with a **Score now** / **Continue** / **Submitted** button.

**3. Create / edit defense** (manager)
- One page containing:
  - the defense info;
  - the proponent formset (1–8 names);
  - the panel form with 3 role dropdowns and weights pre-filled from settings.
- Validation: three different panelists; weights must total exactly 100.
- If a role is reassigned to another person, delete the old person's evaluation for that role.

**4. Evaluate** (panelist) — this is the core screen
- **Header:** institution block and form title (from `INSTITUTION`), project title, proponents,
  panelists, schedule.
- **Rubric tables:** grouped by section, with the 5→1 descriptors shown for each criterion.
- **Ratings:** large tappable 1–5 radio buttons.
- **Oral criteria (5 and 6):** one row of radios **per proponent**.
- **Live subtotals:** A, B, C, FINAL and the provisional verdict update in the browser as the panelist
  rates. The JS must use the same formula; the server recomputes on save.
- **Comments:** a textarea.
- **Buttons:** **Save draft** (partial ratings allowed) and **Submit**.
  - Submit requires every rating and asks for confirmation.
  - After submitting, the form is read-only. Only a manager can unlock it.
- Reject edits when the defense is closed.

**5. Results** (managers always; panelists after completion)
- **Panelist table:** one row per panelist with role, weight, A, B, C, FINAL, verdict and submitted time.
- **Consolidated block:**
  - group score and verdict, styled like the form's 4 checkboxes with the matching one checked;
  - a per-proponent table with each proponent's score and verdict.
- **Comments:** all three panelists' comments.
- **Live updates:** `static/js/results.js` polls a JSON status endpoint every 5 seconds. It updates the
  submission chips and reloads when the last evaluation comes in.

**6. Print views** (`@media print`, A4/Letter, no nav)
- **Summary sheet:** header, computation table, decision, comments, and 3 "Signature Over Printed Name"
  lines (one per panelist).
- **Individual form:** one panelist's filled form, replicating the paper layout.

**7. Panelist accounts** (manager)
- List and create/edit: prefix, first name (with middle initial), last name, suffix, username, password,
  "can manage" checkbox.

**8. Scoring settings** (manager)
- Default weights (must total 100) and the 3 cutoffs (must strictly decrease, within 1–5).

**9. Django admin**
- Register all models. `Defense` gets `Proponent` and `PanelAssignment` inlines.

**10. Management command `load_demo`**
- Creates 3 demo panelists (password `demo1234`) and one demo defense with 2 proponents.
- Fills in ratings that reproduce the worked example.

## 7. File map (already scaffolded)

```
capstone_scoring/
├── AGENT_PROMPT.md            ← this file
├── README.md                  ← update: setup + LAN run steps for Windows
├── requirements.txt
├── manage.py
├── run_lan.py / run_lan.bat   ← LAN launcher
├── docs/rubric.md             ← rubric source of truth
├── capstone_scoring/          ← project settings (done), urls (done), wsgi, asgi
├── defense/
│   ├── models.py  scoring.py  forms.py  views.py  urls.py  admin.py
│   ├── context_processors.py  (done)
│   ├── tests.py
│   ├── migrations/
│   ├── management/commands/seed_rubric.py, load_demo.py
│   ├── templatetags/defense_extras.py
│   └── templates/defense/  dashboard, defense_form, evaluate, results,
│                           print_results, print_form, panelist_list,
│                           panelist_form, settings_form
├── templates/base.html, templates/registration/login.html
└── static/css/app.css, static/js/results.js
```

## 8. Tests and acceptance (`defense/tests.py`)

**Required tests**
- The worked example gives A 1.95, B 0.80, C 1.55, FINAL 4.30, verdict MINOR.
- Verdict boundaries: 4.50 → PASSED, 4.49 → MINOR, 3.50 → MINOR, 3.49 → MAJOR, 2.50 → MAJOR,
  2.49 → FAILED.
- Weighted consolidation with unequal panelist finals and 35/35/30 weights matches a hand-computed value.
- Per-proponent scores differ when oral ratings differ, while A and B stay shared.
- No consolidated result exists until all 3 have submitted.
- A panelist cannot open another panelist's evaluation or a defense they aren't assigned to (403).
- Submit is rejected when any rating is missing. Draft save accepts partial ratings.

**Done means**
- `python manage.py migrate && python manage.py load_demo && python manage.py test` all pass.
- `python manage.py check` is clean.
- You logged in as each demo panelist and confirmed the results page shows 4.30 / PASSED with MINOR
  REVISIONS.

## 9. Working rules

- Build in this order: models + migrations + seed → `scoring.py` + tests → forms/views/templates →
  print views → `load_demo` → README.
- Run the tests after the scoring step, before any UI work.
- Keep business logic out of templates and views; views call `scoring.py`.
- Don't rename existing files or move the rubric. If something in the rubric looks wrong, flag it in
  the README instead of silently changing it.
