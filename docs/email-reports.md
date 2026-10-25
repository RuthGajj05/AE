# Email reports and fast research

What was added, how it works, and what is still open. Everything here lives in `agent/` and `tests/`.

## What was built

1. **Fast research mode** (`agent/fast_competitors.py`; originally a `--fast` flag, now the advisor's only workflow).
   The full pipeline went from about 172 s to about 40 s on the sample bakery.
   The old flow had one agent research every competitor and then write one very long answer (54 s of the
   competitor step); the advice step was another 64 s. Now each competitor gets its own small agent, all running
   in parallel, and the advice step uses a faster model. Competitor agents also look up prices for the owner's
   best-selling items, so the comparison covers the right products.
2. **Email delivery of the report** (`agent/notify.py`, `--email` and `--email-preview` flags).
   HTML plus plain-text email: snapshot, combined impact estimate, and every tip with the action, the evidence
   from the owner's data and from the market, and the math. Sends through Resend when `RESEND_API_KEY` and
   `RESEND_FROM` are set (the same keys the competitor alerts use), otherwise SMTP.
3. **Report-by-email API** (`agent/api.py`). The user enters their business and email; the research runs in the
   background and the report is emailed when it is ready, so nobody waits on a loading screen.
4. **Sales data is optional.** Without it, the advice rests on competitor research and the owner's online
   presence, dollar estimates are left blank, and the caveats say that sales data would sharpen the advice.

## How it works

```
POST /api/report-email  ->  202 {id}  (instant)
   background job:  research (parallel, ~20 s)  ->  advice (~20 s)  ->  save reports/<name>-<id>-advisor.json
                    ->  email the owner  ->  status = done
GET  /api/report-email/{id}  ->  {status, emailed, error, report}
```

- The report is saved before the email is sent, so a mail failure never loses it.
- "done" is only reported after the email attempt, so the status never shows done-but-not-yet-emailed.
- If email is not configured the job still finishes, with `emailed: false` and a plain-English note.
- One recipient only; lists and header-injection attempts are rejected. Report text comes from web pages and model
  output, so it is HTML-escaped. No tracking links or pixels.
- Rate limits (in memory): one report per address per 10 minutes, 30 per hour overall
  (`EMAIL_COOLDOWN_SECS`, `MAX_REPORTS_PER_HOUR`).

## Measured

| Step | Before | After (fast research) |
|---|---|---|
| Competitor research | 108 s | 17-19 s |
| Advice | 64 s | 22-27 s |
| Whole pipeline | 172 s | 39-46 s |
| API request, no sales file, end to end | n/a | 36 s, 8 competitors, 5 tips |

One sample bakery, a handful of runs: indicative, not a benchmark. Tests (`tests/test_notify.py`,
`tests/test_api.py`, 42 checks) mock the model calls and mail, so they cost nothing and send nothing.

## Known limits

- **No real email has been sent yet.** It needs the Resend login in `.env`. Resend's test sender only delivers to
  the account owner's own address until a domain is verified.
- The frontend does not call the API yet (see `docs/frontend-integration.md`).
- Fast mode picks its competitor shortlist from less context, so it sometimes picks shops a little farther away
  than the default agent. Check the shortlist for a demo. Haiku is faster still but less careful (it once took a
  delivery-app rating for the shop's own); the default is Sonnet 5.5 (`FAST_MODEL` to change).
- Jobs are kept in memory and lost on restart (the report JSON is saved in `reports/`).
- The email is long because it carries every tip's evidence. A short version with a link to the full report would
  read better once reports have a hosted page.
- `crumbs-backend` already has competitor-change alerts by text and email (`agent/monitor.py`). This is a
  different thing (the full report), but the two should be checked against each other before merging.
