# Backend checks

Run from the project root after installing dependencies:

```sh
node --test tests/backend.test.mjs tests/inventory.test.mjs
```

The suite compiles the relevant TypeScript modules in memory using the existing TypeScript dependency. It uses Node's built-in test runner. It makes no network requests and needs no API credential.

Coverage includes URL validation and domain ownership, actual fetch-result filtering, source IDs and quote verification, missing evidence, input-order preservation, bounded two-stage research, provider error handling, request rejection, concurrent request gating, optional questionnaire validation, normalized owner-context snapshots, and UTF-8 request-size handling. Owner answers are checked separately from fetched website evidence; they never create source IDs or replace the requirement for readable websites.

These checks validate program behavior. They do not establish that model-generated claims are semantically correct or that a live provider and deployed website are reachable; those require separate end-to-end verification.

Square inventory checks cover paginated catalog/count reads, per-location availability and tracking, unknown/zero/fractional counts, safe errors, fixed API hosts, route access/cache handling, local thresholds, and CSV escaping. Square responses are mocked; these tests do not establish a real merchant connection.
