# Capstone Defense Scoring System (LAN)

A LAN-based Django + SQLite app for scoring the ITE capstone final defense at Colegio de Kidapawan, Inc.

- Examiner 1, Examiner 2 and the Research Coordinator each score from their own workstation or phone.
- Each panelist scores individually, exactly like the paper form: A (System), B (Manuscript) and
  C (Oral Defense, rated per student), each criterion on the 5-point scale
  Excellence / Very Good / Good / Fair / Poor.
- Each panelist's FINAL (A + B + C) gets a result: **PASSED**, **PASSED with MINOR REVISIONS**,
  **PASSED with MAJOR REVISIONS**, or **FAILED**.
- Once all three have submitted, the panel's decision is the result that **at least 2 of the 3
  panelists** agree on. The same rule is applied to each student. Panelists are not weighted.
- It works fully offline. There are no CDNs; all CSS, JS and the Archivo font (SIL Open Font License, `static/fonts/OFL.txt`) are in `static/`.

## Setup (Windows)

Install Python 3.11 or newer from python.org and tick **"Add python.exe to PATH"**. Then, in the
project folder:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
```

`migrate` also loads the 6 rubric criteria from `docs/rubric.md`. If you edit that file, re-run
`python manage.py seed_rubric`.

To try the system with sample data:

```
python manage.py load_demo
```

This creates three demo accounts, all with the password `demo1234`:

| Username | Role | Access |
|---|---|---|
| `examiner1` | Examiner 1 | Panelist |
| `examiner2` | Examiner 2 | Panelist |
| `coordinator` | Research Coordinator | Manager |

It also creates one demo defense with 2 proponents that all three have already scored. Its results
page shows each panelist at **4.30 / PASSED with MINOR REVISIONS**, so the panel's decision is
**PASSED with MINOR REVISIONS (3 of 3 panelists)**. This is the worked example from the
specification.
Running `load_demo` again recreates the demo defense.

Run the checks and tests:

```
python manage.py check
python manage.py test
```

## Run on the LAN

On the host machine, either run `python run_lan.py` (with `.venv` activated) or double-click
`run_lan.bat`. The launcher applies any pending migrations, then prints the address to use, for example:

```
  Panelists open: http://192.168.1.23:8000
```

Panelists open that address in a browser on any device connected to the same network (Wi-Fi or
LAN). Press Ctrl+C in the window to stop the server. To use another port, run
`python run_lan.py 8080`.

If the other devices can't connect, allow Python through Windows Firewall on the host for private
networks: Windows Security → Firewall & network protection → Allow an app through firewall →
python.exe → tick *Private*. Also make sure the host's network profile is set to *Private*, not
*Public*.

> `run_lan.bat` uses `.venv\Scripts\python.exe` when the `.venv` folder exists, and falls back to
> the system `python` otherwise.

For step-by-step instructions for the person running the host PC, see [HOW_TO_RUN.md](HOW_TO_RUN.md).

## Day-of-defense workflow

1. **Manager setup.** The Research Coordinator, or any account with *Can manage*, does this:
   - Under **Panelists**, create an account for each examiner: prefix, name with middle initial,
     suffix, username and password.
   - Under **New defense**, enter the title, schedule and venue, add 1–8 proponents, and pick the
     three panelists.
2. **Scoring.** Each panelist logs in, clicks **Score now**, and taps 1–5 for every criterion.
   Criteria 5 and 6 are rated once per proponent.
   - Subtotals and the provisional verdict update live as they rate.
   - **Save draft** keeps partial ratings.
   - **Submit** requires every rating and asks for confirmation.
   - After submitting, the panelist can still edit and **Save changes** (every item must stay rated)
     until scoring is closed. The results page reloads itself when a submitted score changes.
3. **Results.** The results page shows each panelist's status (Not started / Draft / Submitted) and
   refreshes itself every 5 seconds. When the third evaluation comes in, it shows:
   - the panel's decision (2 of 3), with the decision boxes ticked;
   - each panelist's A, B, C, FINAL and result;
   - each student's FINAL from each panelist and that student's decision (2 of 3);
   - all comments.
4. **Print.**
   - **Print summary** gives the summary sheet with three "Signature Over Printed Name" lines.
   - **Form** (managers) or **Print my form** (panelists) gives one panelist's filled-in form in the
     paper layout.
   - Both are set up for A4.
5. **Corrections and closing.** Panelists fix their own submitted scores while scoring is open. A
   manager can also **Return to draft** a submitted evaluation. **Close scoring** on the Defenses
   page makes all of that defense's forms read-only, including submitted ones.

## How scores are computed

All math is in `defense/scoring.py`, using `Decimal` throughout. `static/js/evaluate.js` mirrors it
for the live subtotals, and the server recomputes everything on save.

- Weighted score of a criterion = rating × weight.
- **A** = criteria 1–3, **B** = criterion 4. Both are rated once for the group.
- **C** = criteria 5–6, rated per proponent.
- A student's FINAL (from one panelist) = A + B + that student's own C.
- Group FINAL (from one panelist) = A + B + the average C. This is the single C on the paper form.
- Each FINAL is rounded to 2 decimals (ROUND_HALF_UP) and given a result, using ≥ cutoffs that you
  can edit in Settings:

| Score | Verdict |
|---|---|
| ≥ 4.50 | PASSED |
| ≥ 3.50 | PASSED with MINOR REVISIONS |
| ≥ 2.50 | PASSED with MAJOR REVISIONS |
| below 2.50 | FAILED |

**Panel's decision: 2 of 3.** Once all three have submitted, the decision is the result that at
least 2 of the 3 panelists gave. This is done for the group and separately for each student, using
each panelist's FINAL for that student. For example:

| | Examiner 1 | Examiner 2 | Coordinator | Decision |
|---|---|---|---|---|
| Group | 3.88 MINOR | 4.65 PASSED | 3.65 MINOR | **MINOR** (2 of 3) |
| Student 2 | 3.45 MAJOR | 4.30 MINOR | 3.30 MAJOR | **MAJOR** (2 of 3) |

Scores are never averaged across panelists, and no panelist counts more than another.

If all three results differ (for example PASSED, MINOR and MAJOR), there is no 2-of-3 agreement.
The system then shows the middle result (MINOR in that example) and flags it on the results page
and the printout so the panel can confirm the decision.

## Rubric notes (flagged, not changed)

`docs/rubric.md` is used exactly as written. These points about the paper form are worth knowing:

1. **Section letters.** The paper form labels the Oral Defense section "B". It is section **C**
   here, as the rubric file already notes.
2. **Gaps in the decision bands.** The paper bands (4.5–5.0, 3.5–4.4, 2.5–3.4, below 2.5) leave
   4.41–4.49 and 3.41–3.49 uncovered. The system uses the ≥ 4.50 / 3.50 / 2.50 cutoffs instead, so
   a 4.45 is PASSED with MINOR REVISIONS and a 3.45 is PASSED with MAJOR REVISIONS. If the
   department reads the bands differently, change the cutoffs in **Settings**.
3. **One C on paper, one C per proponent here.** The paper form has a single C value. Here, oral
   criteria are rated per proponent. The group's C is the average of the proponents' C values; each
   proponent also gets their own FINAL and verdict.
4. **Wording.** Criterion 1, descriptor 1 reads "non functional" (normally "non-functional"). The
   text is shown as written.

## Other notes

- **Changing the panel.** If you give a role to a different person, the previous person's
  evaluation for that role is deleted. Swapping two examiners counts as reassigning both roles.
- **Adding proponents.** If you add a proponent after evaluations were submitted, those
  evaluations go back to *Draft* so the panelists can rate the new proponent.
- **Django admin.** The admin at `/admin/` is meant for superusers (`createsuperuser`).
  *Can manage* accounts use the app's own pages instead. Every user, including a superuser, can be
  put on a panel.
- **Deactivating criteria.** Turning off a criterion (`is_active`) in the admin also changes
  results that are already computed. Leave the rubric alone once defenses have been scored.
- **Concurrent saves.** SQLite waits up to 20 s for a lock, and each save is one short transaction,
  so three panelists saving at the same moment is fine.
- **Python version.** `requirements.txt` pins Django 5.x. Install it in the `.venv` as above,
  even if a newer Django is installed globally.
