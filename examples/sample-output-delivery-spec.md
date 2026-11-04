<!-- Produced by `sdlc-assistant demo --auto-approve`. The agent outputs are the bundled demo fixtures (sdlc_assistant/mock_data), so token counts are estimates. A live run with your API key will word things differently. -->

# Delivery Spec

**Status:** approved · gate1: approved, gate2: approved, gate3: approved · QA feedback loops used: 1

## Feature request

> Employees should be able to request time off. They pick the dates, see how many vacation days they have left, and submit the request. Their manager gets notified and can approve or reject it. Approved time off should show up on the team calendar.

## 1. Requirement

**Problem:** Employees need a self-service way to request vacation and get a manager decision, so time off is tracked against their balance and visible to the team.

**In scope**
- Employee can view their remaining vacation balance
- Employee can select a start and end date for a request
- Employee can submit a time-off request
- System checks the request against the remaining balance
- Manager is notified when a request is submitted
- Manager can approve a pending request
- Manager can reject a pending request
- Employee is told the outcome of their request
- Approved time off appears on the team calendar

**Out of scope**
- Accrual rules and how balances are calculated
- Leave types other than vacation (sick, parental, unpaid)
- Editing or cancelling a request after submission
- Multi-level or delegated approvals
- Payroll integration

**Assumptions**
- Each employee has exactly one manager who approves their requests
- Balances are counted in whole working days; weekends are not deducted
- A balance service already exists and is the source of truth
- Employees and managers are already authenticated users of the app

**Open questions**
- Do pending (not yet approved) requests reduce the balance shown to the employee?
- Is the manager notified in-app, by email, or both?
- Must the manager give a reason when rejecting?
- Are public holidays excluded from the day count, and from which holiday calendar?
- Who can see the team calendar: only the team, or the wider company?

## 2. User stories

**US-1** — As an employee, I want to see my remaining vacation balance, so that I know how much time off I can request.
  - `US-1.AC1` Given I am logged in and have 12 vacation days remaining, When I open the time-off page, Then I see '12 days remaining'

**US-2** — As an employee, I want to pick a start and end date, so that I can say exactly when I'll be away.
  - `US-2.AC1` Given I am on the request form, When I choose an end date on or after the start date, Then the number of working days requested is shown
  - `US-2.AC2` Given I am on the request form, When I choose an end date before the start date, Then I see an error and cannot submit

**US-3** — As an employee, I want to submit my request, so that my manager can review it.
  - `US-3.AC1` Given valid dates within my remaining balance, When I submit, Then a request is created with status 'Pending'
  - `US-3.AC2` Given the requested working days exceed my remaining balance, When I submit, Then the submission is blocked with a message and no request is created

**US-4** — As a manager, I want to be notified of a new request, so that I can review it promptly.
  - `US-4.AC1` Given an employee on my team submits a request, When it is created, Then I receive a notification linking to the request

**US-5** — As a manager, I want to approve a pending request, so that my team member can take the time off.
  - `US-5.AC1` Given a pending request from my team, When I approve it, Then its status becomes 'Approved', the employee is notified, and their balance is reduced by the requested days

**US-6** — As a manager, I want to reject a pending request, so that time off that doesn't work for the team isn't granted.
  - `US-6.AC1` Given a pending request from my team, When I reject it with an optional reason, Then its status becomes 'Rejected', the employee is notified with the reason, and their balance is unchanged

**US-7** — As a team member, I want approved time off on the team calendar, so that we can plan around absences.
  - `US-7.AC1` Given a request is approved, When anyone on the team opens the team calendar, Then the employee is shown as away on each requested date, and pending or rejected requests are not shown

## 3. Test cases

| ID | Criterion | Type | Case |
| --- | --- | --- | --- |
| T-1 | US-1.AC1 | positive | Setup: employee with 12 days remaining. Action: open the time-off page. Expected: '12 days remaining' is shown. |
| T-2 | US-1.AC1 | negative | Setup: the balance service is unavailable. Action: open the time-off page. Expected: a clear 'balance unavailable, try again' message, not a blank or zero balance; submit is disabled. |
| T-3 | US-1.AC1 | edge | Setup: new employee with 0 days remaining. Action: open the time-off page. Expected: '0 days remaining' is shown, not a negative number or empty value. |
| T-4 | US-2.AC1 | positive | Setup: request form. Action: choose Mon 2 Mar to Fri 6 Mar. Expected: '5 working days' is shown. |
| T-5 | US-2.AC1 | negative | Setup: request form. Action: choose a range that starts in the past. Expected: an error says past dates can't be requested. |
| T-6 | US-2.AC1 | edge | Setup: request form. Action: choose Fri 6 Mar to Mon 9 Mar (spans a weekend). Expected: '2 working days' is shown. |
| T-7 | US-2.AC2 | positive | Setup: request form. Action: choose end date 1 Mar, start date 5 Mar. Expected: error 'End date must be on or after start date'; submit disabled. |
| T-8 | US-2.AC2 | negative | Setup: request form showing the end-before-start error. Action: correct the end date to 5 Mar. Expected: error clears and submit becomes enabled. |
| T-9 | US-2.AC2 | edge | Setup: request form. Action: choose the same day for start and end. Expected: accepted as a 1-day request, no error. |
| T-10 | US-3.AC1 | positive | Setup: 12 days remaining. Action: submit a valid 3-day request. Expected: request created with status 'Pending' and shown in 'My requests'. |
| T-11 | US-3.AC1 | negative | Setup: valid request form. Action: submit while the network drops. Expected: no duplicate is created on retry; the employee sees whether the request was saved. |
| T-12 | US-3.AC1 | edge | Setup: 3 days remaining. Action: submit a request for exactly 3 working days. Expected: allowed; request created as 'Pending'. |
| T-13 | US-3.AC2 | positive | Setup: 3 days remaining. Action: submit a request for 4 working days. Expected: blocked with 'Not enough vacation days'; no request created. |
| T-14 | US-3.AC2 | negative | Setup: 3 days remaining. Action: bypass the form and post a 4-day request directly to the API. Expected: the server rejects it; no request created. |
| T-15 | US-3.AC2 | edge | Setup: 0 days remaining. Action: submit a 1-day request. Expected: blocked with the balance message. |
| T-16 | US-4.AC1 | positive | Setup: employee on the manager's team. Action: submit a request. Expected: the manager receives a notification that links to that request. |
| T-17 | US-4.AC1 | negative | Setup: employee in a different team. Action: submit a request. Expected: this manager receives no notification. |
| T-18 | US-4.AC1 | edge | Setup: employee whose manager record is missing. Action: submit a request. Expected: request is still created and the case is logged for HR; the employee is told approval may be delayed. |
| T-19 | US-5.AC1 | positive | Setup: pending 3-day request, employee has 12 days. Action: manager approves. Expected: status 'Approved', employee notified, balance shows 9 days. |
| T-20 | US-5.AC1 | negative | Setup: pending request from another team. Action: a different manager tries to approve via direct URL. Expected: access denied; status unchanged. |
| T-21 | US-5.AC1 | edge | Setup: request already approved. Action: manager clicks approve again. Expected: no change; balance is not reduced twice. |
| T-22 | US-6.AC1 | positive | Setup: pending 3-day request. Action: manager rejects with reason 'Team offsite that week'. Expected: status 'Rejected', employee notified with the reason, balance unchanged. |
| T-23 | US-6.AC1 | negative | Setup: pending request from another team. Action: a different manager tries to reject via direct URL. Expected: access denied; status unchanged. |
| T-24 | US-6.AC1 | edge | Setup: pending request. Action: manager rejects with no reason. Expected: allowed; employee is notified that the request was rejected without a reason. |
| T-25 | US-7.AC1 | positive | Setup: 3-day request approved. Action: a teammate opens the team calendar. Expected: the employee is shown as away on all 3 dates. |
| T-26 | US-7.AC1 | negative | Setup: one pending and one rejected request. Action: open the team calendar. Expected: neither appears. |
| T-27 | US-7.AC1 | edge | Setup: approved request spanning a weekend. Action: open the team calendar. Expected: shown on the working days only, consistent with the day count. |
| T-28 | US-5.AC1 | edge | Integration (US-5 → US-1 → US-3): employee with 3 days has a 3-day request approved, then opens the balance page and tries a 1-day request. Expected: balance shows 0 and the new request is blocked. |

## 4. QA gap report

- **MEDIUM** · inconsistency (US-1.AC1, US-3.AC2, requirement): Open question 1 is still unresolved: if pending requests don't reduce the balance, an employee could submit two requests that together exceed it. Add a rule (count pending days against the balance at submit time) or confirm the risk is acceptable.
- **LOW** · untested_criterion (US-4.AC1): US-4.AC1 says 'a notification' but the channel (in-app, email, both) is an open question; tests T-16 to T-18 will need updating once it's decided.

**Mechanical coverage check:** 9 of 9 acceptance criteria have positive, negative and edge tests.

## Run log (mock mode: canned outputs, estimated tokens)

| Agent | Model | Input tokens | Output tokens | Cost |
| --- | --- | --- | --- | --- |
| requirements_analyst | `claude-sonnet-5-5` | 331 | 410 | $0.0048 |
| story_writer | `claude-haiku-5-5` | 656 | 580 | $0.0004 |
| test_designer | `claude-sonnet-5-5` | 925 | 723 | $0.0091 |
| qa_verifier | `claude-opus-5-5` | 2,137 | 423 | $0.0170 |
| story_writer | `claude-haiku-5-5` | 813 | 780 | $0.0005 |
| test_designer | `claude-sonnet-5-5` | 1,313 | 1,649 | $0.0191 |
| qa_verifier | `claude-opus-5-5` | 3,184 | 168 | $0.0161 |

**Total:** $0.0669 · same tokens on the premium model for every step: $0.1321 (49% saved by routing)
