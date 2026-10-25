# AE

## Nearby prototype

Nearby helps small-business owners compare their website with one to three competitors, review recommendations with sources, and edit the accompanying drafts.

### Run locally

Requires Node.js **22.13+** and npm.

```sh
git clone https://github.com/jaggerbaldevia-star/AE.git
cd AE
npm run install:ci
npm run dev
```

Open the local URL printed by the dev server. The Seattle bakery example works without an API credential. For live research, create an untracked `.dev.vars` file using `.env.example` as a template, then set your own `ANTHROPIC_API_KEY` there. Keep real credentials out of Git.

### What works

- Website and competitor inputs, plus an optional business goal and questionnaire about the business, customers, existing efforts, and time, budget or capacity constraints.
- Claude research restricted to the supplied business domains.
- Up to three recommendations with source links and retrieval dates.
- Form inputs saved in the browser before research runs, plus an owner-provided business brief kept separate from website evidence.
- Editable drafts with browser autosave, copy, and Markdown export, including the submitted business brief.
- Explicit missing-evidence, stale-source, and provider-error handling.

### Checks

```sh
npx tsc --noEmit
node --test tests/backend.test.mjs
npm run build
```

### Deployment and data

The questionnaire is optional. Owners still need their website and one to three competitor websites. Answers help tailor recommendations to the owner's goal and constraints; they are self-reported information, not independently verified facts.

The prototype is intended for local use or a private Sites deployment. The research API relies on the private Sites access boundary; add server-side authentication and durable usage limits before deploying it publicly elsewhere. This repository contains no live Site identity or API credential. Form inputs, reports and draft edits save in the browser. URLs, goals and questionnaire answers are sent to Claude only when research is submitted; do not enter customer personal data. Drafts are never emailed or posted automatically.

See [the implementation and setup guide](NEARBY.md), [backend checks](tests/README.md), and [the original project meeting notes](thought%20overview).
