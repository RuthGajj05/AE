# Nearby

A working private prototype for small-business owners: enter your website and one to three competitor websites, receive source-linked recommendations, and edit the accompanying drafts.

## Try it

1. Start the app locally using the setup instructions below, or open your own private Sites deployment.
2. Enter your website and one to three independent competitor websites using public HTTPS addresses. Direct menu or service pages work too.
3. Optionally add the business name, goal, and short business questionnaire, then run research. Allow about 1–3 minutes.
4. Review your business brief, the comparison, source links, timestamps, and limitations.
5. Edit the draft for each recommendation. Copy it or download the report. Confirm placeholders and business facts before publishing anything.

The separately labeled Seattle bakery example is a saved research example. It does not run a fresh scan. Live errors never silently fall back to that example.

## Inventory with Square

Open **Inventory** to track stock by location. Search item variations, filter low or missing stock, set browser-local low-stock thresholds, and export a CSV. The explicit sample works without credentials. Connect a Square sandbox account with a server-side `SQUARE_ACCESS_TOKEN`; see [Square setup and data semantics](SQUARE.md). Counts are read-only snapshots refreshed on request. This is a single-merchant connection, not multi-business OAuth onboarding.

## Optional business questionnaire

Owners can describe their business type and location, products or services, target customers, existing offers or marketing, and constraints such as time, budget, or capacity. The goal field explains what they want to improve. Every questionnaire answer is optional; the business website and at least one competitor website are still required.

Form inputs save in this browser before research runs. The report keeps a snapshot of the submitted answers, labeled as owner-provided information rather than independently verified website evidence. That brief is included in the Markdown export. Recommendations use these answers to account for the owner's constraints and avoid proposing work already in place.

## How live research works

The server calls Claude Sonnet 5.5 with Anthropic's web-fetch tool, restricted to the supplied business domains and eight fetches. It collects actual successful text results, including the source URL and retrieval time. A second Claude call produces structured recommendations using those pages and the owner-provided business brief, while keeping the two kinds of information distinct. The server validates the result and rejects unknown source IDs and mixed business attribution. Displayed excerpts are checked against the retrieved text; invalid model-proposed excerpts are replaced by an actual page excerpt.

The app requires readable evidence for the owner's business and at least one competitor. If other sites cannot be read, the report labels the comparison as partial. Web-fetch may serve cached content. A source being retrieved is not a guarantee that every model interpretation is correct; owners can inspect the linked originals.

## Data and access

- The original prototype runs on an owner-private Site. Its shared API relies on Sites authentication and access control. This source export does not include that deployment identity. Keep your deployment private, or add server-side authentication and per-user quotas before exposing `/api/research`. Multi-customer access also requires tenant storage.
- The Claude key is a server-side Sites secret named `ANTHROPIC_API_KEY`. It is never sent to the browser or placed in source control.
- URLs, the optional name, goal and questionnaire answers, and retrieved public website text are sent to Anthropic when the owner submits a research request. Typing or saving answers locally does not send them to Claude. Do not enter customer personal data or confidential customer information.
- Form inputs, reports, and edited drafts are stored in this browser's local storage. They are not synchronized between devices. Clearing browser data removes them.
- Nothing is emailed, posted, or changed on a business website automatically.
- Research has a 210-second server deadline and bounded fetch/output budgets. The prototype limits overlapping/repeated requests per running server instance. It does not yet provide a durable account-wide quota or billing system.

## Local development

Use Node.js 22.13 or newer and npm. The Sites portable starter is retained.

```sh
npm run install:ci
npm run dev
```

The dev server prints its local URL. Local sign-in is supplied by the Sites development plugin. For live local research, configure an untracked `.dev.vars` file containing `ANTHROPIC_API_KEY`. Configure the production secret using Sites environment settings.

Run TypeScript checking and the offline test runner described in `tests/README.md`.

For publication, use the Sites `site-workflow.mjs` and `build-site.mjs` helpers. They keep the pushed source commit, packaged worker, and saved Site version consistent. Register a new private Site and put its returned project ID in `.openai/hosting.json`; this export intentionally contains no existing Site ID. Preserve the starter's `sites()` integration. For independent hosting, implement authentication and rate limits before exposing the research API.

## Useful next steps

Pilot with a handful of owners to evaluate recommendation usefulness and source accuracy. Before sharing the service with multiple businesses, add explicit user isolation, durable per-user usage budgets, cross-device saved reports, deletion controls, and a small regression set of real website research cases. Competitor discovery, scheduled monitoring, direct publishing, paid subscriptions, and guaranteed business outcomes are outside this prototype.

## API references

- [Anthropic web-fetch tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-fetch-tool)
- [Claude model overview](https://platform.claude.com/docs/en/models/overview)
