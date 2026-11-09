# How to Run the Capstone Defense Scoring System

This guide is for the person who runs the **host PC** at the defense venue. The host PC runs the
system; Examiner 1, Examiner 2 and the Research Coordinator score from their own laptops or phones
on the same network. No internet connection is needed.

---

## 1. One-time setup on the host PC

Skip this section if the `.venv` folder already exists in the project folder (it does on the PC
where the system was first installed).

1. Install **Python 3.11 or newer** from python.org. On the first installer screen, tick
   **"Add python.exe to PATH"**.
2. Open the project folder (`capstone_scoring`) in File Explorer, click the address bar, type `cmd`
   and press Enter. A Command Prompt opens in that folder.
3. Run these commands one at a time:

   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python manage.py migrate
   ```

4. Create the administrator account:

   ```
   python manage.py createsuperuser
   ```

   Enter a username (for example `admin`), leave the email blank, and type a password twice. The
   password does not show while you type.

---

## 2. Start the system (every defense day)

1. Connect the host PC to the venue's Wi-Fi or LAN, the same network the panelists will use.
2. In the project folder, **double-click `run_lan.bat`**.
3. A black window opens and shows something like:

   ```
   ============================================================
     Capstone Defense Scoring System
     Panelists open: http://192.168.254.103:8000
     On this PC:     http://127.0.0.1:8000
     Press Ctrl+C to stop the server.
   ============================================================
   ```

4. Write the **"Panelists open"** address on the board or send it to the panelists. If more than one
   address is listed, use the first one; the others are usually virtual network adapters.
5. **Keep the window open** for the whole defense. Closing it stops the system.

> **First run only:** Windows may ask whether to allow Python on the network. Tick **Private
> networks** and click **Allow**.

---

## 3. Sign in

Open the address in any browser (Chrome, Edge or Firefox), on the host PC or on any device on the
same network.

| Who | Signs in with | What they can do |
|---|---|---|
| Administrator | the `createsuperuser` account | Everything, including the Django admin at `/admin/` |
| Research Coordinator | an account with **Can manage** ticked | Create defenses and accounts, change settings, close scoring, see all results |
| Examiners | their own panelist account | Score the defenses they are assigned to; see results once all 3 have submitted |

**Change the administrator password** after the first sign-in: open `/admin/`, click
**Change password** in the top-right corner.

---

## 4. Before the defense: set it up

Signed in as the administrator or Research Coordinator:

1. **Panelists → + New panelist.** Create an account for each examiner. Enter the prefix (Engr.,
   Dr.), first name with middle initial, last name, suffix (LPT, CCpE), a username and a password.
   - Tick **Can manage** for the Research Coordinator.
   - Give each examiner their own username and password.
2. **New defense.** Enter:
   - the project title, date, time and venue;
   - the proponents' full names (1–8; use **+ Add proponent** for more rows);
   - the three panelists (three different people).
3. Click **Save defense**. It appears on the dashboard.

---

## 5. During the defense

- Each panelist signs in and clicks **Score now** next to the defense on the **Defenses** page.
- They tap a rating from 5 to 1 for each criterion. Criteria 5 and 6 have one row per proponent.
- Their subtotals and provisional verdict update as they rate.
- **Save draft** keeps partial work. **Submit evaluation** requires every rating and asks for
  confirmation.
- On the defense's **Status / Results** page, the coordinator can watch the submissions come in
  (Not started / Draft / Submitted). The page refreshes on its own every 5 seconds.

Panelists can still change their scores **after submitting**, as long as scoring is open: they open
the form again (**✓ Edit my scores** on the Defenses page), change the ratings or comments, and click
**Save changes**. Every item must stay rated, and the results update right away. If needed, the
coordinator can also click **Return to draft** next to a panelist on the results page; that
evaluation then stops counting until the panelist submits it again.

---

## 6. After all three submit

The results page shows:

- the Panel's Decision (PASSED / MINOR / MAJOR / FAILED): the result at least **2 of the 3**
  panelists gave;
- each student's score from each panelist, and that student's own decision (also 2 of 3);
- each panelist's A, B, C and FINAL;
- all comments.

If all three panelists' results differ (for example PASSED, MINOR and MAJOR), the page shows the
middle result and a warning, and the panel should agree on the final decision.

To print:

- **Print summary:** the summary sheet with three signature lines.
- **Form** (next to each panelist) or **Print my form:** one panelist's completed form.

Click **Print** on the page. Choose A4 paper; turning off "Headers and footers" in the print dialog
gives a cleaner sheet.

When the panel has agreed on the final decision, click **Close scoring** on the Defenses page.
After that no one can change their ratings, including ones they already submitted.

To remove a defense entirely, for example a test entry or one created by mistake, click **Delete**
in its row on the **Defenses** page or at the bottom of its **Edit** page. This permanently deletes its students,
panel and **all scores and comments**, so print the summary sheet first if you need a record.
Panelist accounts are not deleted.

---

## 7. Stop the system

Click the black server window and press **Ctrl+C**, then close the window. All data is kept for the
next time.

---

## 8. Back up the data

All scores, accounts and defenses are stored in one file: **`db.sqlite3`** in the project folder.

- To back up, stop the system and copy `db.sqlite3` to a USB drive or another folder. Put the date
  in the copy's name, for example `db-2026-11-12.sqlite3`.
- To restore, stop the system, put the backup copy back in the project folder, and rename it to
  `db.sqlite3`.

---

## 9. Troubleshooting

| Problem | What to do |
|---|---|
| Panelists' devices can't open the address | Make sure they're on the **same Wi-Fi/LAN** as the host. Allow Python through Windows Firewall: Windows Security → Firewall & network protection → Allow an app through firewall → **python.exe** → tick **Private**. Set the host's network to **Private**, not Public. |
| No "Panelists open" address is shown | The host isn't connected to a network. Connect it, then start `run_lan.bat` again. You can also run `ipconfig` and use the IPv4 address with `:8000`. |
| The address stopped working mid-day | The host's IP may have changed (for example after reconnecting to Wi-Fi). Restart `run_lan.bat` and share the new address. |
| "That port is already in use" | The system is already running in another window, so use that one. Or start on a different port: open Command Prompt in the folder and run `.venv\Scripts\python run_lan.py 8080`. |
| A panelist forgot their password | Coordinator: **Panelists → Edit**, type a new password, and save. |
| Remove a panelist account | **Panelists → Delete**. This only works if the person is on no defense panel (the **Panels** column shows 0), so their scores are never lost. Otherwise, assign someone else to their role in that defense first, or untick **Active** under **Edit** so they can't sign in. |
| A panelist can't see the defense | They aren't on its panel. Coordinator: **Edit** the defense and check the three role dropdowns. |
| Submit says ratings are missing | Scroll up; unrated rows have a dashed border. Every criterion needs a rating, and criteria 5 and 6 need one for **each** proponent. |
| Results don't show yet | Scores appear only after **all three** panelists submit. The status chips show who is still pending. |

---

## Quick reference: commands

Run these in a Command Prompt opened in the project folder:

| Task | Command |
|---|---|
| Start the server | `run_lan.bat` (or `.venv\Scripts\python run_lan.py`) |
| Create another administrator | `.venv\Scripts\python manage.py createsuperuser` |
| Reset a password from the command line | `.venv\Scripts\python manage.py changepassword <username>` |
| Load the demo data (for practice) | `.venv\Scripts\python manage.py load_demo` |
| Run the automated tests | `.venv\Scripts\python manage.py test` |
