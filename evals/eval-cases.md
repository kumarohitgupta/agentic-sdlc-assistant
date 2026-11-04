# Evaluation cases

A small, fixed set of feature requests for measuring the pipeline. The same cases live in machine-readable form in [`cases.json`](cases.json), which `sdlc-assistant eval` runs. Score the results with the rubric in [`../docs/evaluation.md`](../docs/evaluation.md). Cases EC-4 and EC-5 contain **planted gaps** to test the QA Verifier.

---

### EC-1 — Password reset
"Users should be able to reset their password if they forget it. Send them an email with a link. The link should expire."

### EC-2 — Export report to CSV
"Managers want to export the team's attendance report as a CSV so they can share it. They should be able to pick a date range."

### EC-3 — In-app notifications
"When something needs a user's attention — an approval, a mention — show them a notification in the app. They should be able to mark it as read."

### EC-4 — Bulk upload (PLANTED GAP)
"HR wants to upload new employees in bulk from a spreadsheet. Show them which rows succeeded and which failed."
- **Planted gap:** the request implies validation of the spreadsheet, but a naive run will write stories for upload + result display and skip *what makes a row fail* (validation rules). The Verifier should flag an uncovered requirement around row validation.

### EC-5 — Two-factor login (PLANTED GAP)
"Add optional two-factor authentication at login using an authenticator app. Users can turn it on in settings."
- **Planted gap:** the happy path (enable 2FA, log in with code) is easy; a naive run typically omits the **recovery / lost-device** path. The Verifier should flag a missing story/tests for recovery codes or lockout.

### EC-6 — Comment on a document
"Let users leave comments on a document and reply to each other. Comments should show who wrote them and when."

---

## How to run
```bash
sdlc-assistant eval              # runs all cases, writes runs/eval-<timestamp>/results.md
sdlc-assistant eval --only EC-4,EC-5
```
Then score each Delivery Spec against the rubric and fill in the results table in `docs/evaluation.md`. To run a case with real human gates instead, use `sdlc-assistant run --feature "<request text>"` and note what you changed at each gate.
