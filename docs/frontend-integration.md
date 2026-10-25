# Frontend: adding "Email me this report"

The report API is its own small server. The frontend talks to it directly; it does not need the other backend.

```sh
.venv/bin/uvicorn api:app --app-dir agent --port 8100      # needs ANTHROPIC_API_KEY and TAVILY_API_KEY in .env
```

Add `VITE_REPORT_API_URL=http://localhost:8100` to the frontend's `.env.local`. Browsers can call it already
(CORS is open).

## Request

```ts
const res = await fetch(`${import.meta.env.VITE_REPORT_API_URL}/api/report-email`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    business: profile.name,                       // required, up to 100 characters
    business_type: 'bakery',                      // required, plain words (see mapping below)
    location: 'Beacon Hill, Seattle',             // required: neighborhood label + city
    email: email,                                 // required, one address
    website: undefined,                           // optional
  }),
})
if (!res.ok) {
  const { error } = await res.json()              // always { error: "plain-English message" }
  showError(error)
  return
}
const { id } = await res.json()                   // 202: research has started
showMessage('Thanks! We will email your report in about a minute.')
```

`business_type` mapping from the frontend's category ids: `bakery` -> `bakery`, `coffee` -> `coffee shop`,
`tacos` -> `taco shop`, `pho` -> `pho restaurant`.

## Response

`202 {"id": "a1b2c3d4e5", "status": "running", "message": "We're researching your market. ..."}`

You do not have to poll: the email is the delivery. If you want an on-screen status, poll
`GET /api/report-email/{id}` every 5 seconds:

```json
{ "status": "running" }
{ "status": "done", "emailed": true,  "error": null, "report": { "...": "full advisor report" } }
{ "status": "done", "emailed": false, "error": "The report is ready, but email isn't set up on this server.", "report": { } }
{ "status": "error", "error": "We couldn't finish the research this time. Please try again." }
```

## Errors (status code -> what to show)

| Code | Meaning | Message comes from the API |
|---|---|---|
| 400 | Email address is not valid | yes |
| 422 | A required field is missing | yes |
| 429 | Same address asked within 10 minutes, or the server is at its hourly cap | yes |
| 404 | Unknown report id | yes |

Show the `error` text as is; it is written for the end user.

## UX notes

- Say what will happen: "We'll email your report in about a minute", and offer a way to see it on screen too.
- Say whose email it is: only send to the address the user typed, and do not pre-fill it.
- The first test email should go to a team member's own address: new senders often land in spam.
