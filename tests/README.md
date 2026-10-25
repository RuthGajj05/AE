# Backend checks

Run from the project root after installing dependencies:

```sh
node --test tests/backend.test.mjs
```

The suite compiles the relevant TypeScript modules in memory using the existing TypeScript dependency. It uses Node's built-in test runner. It makes no network requests and needs no API credential.

Coverage includes URL validation and domain ownership, actual fetch-result filtering, source IDs and quote verification, missing evidence, input-order preservation, bounded two-stage research, provider error handling, request rejection, and concurrent request gating.

These checks validate program behavior. They do not establish that model-generated claims are semantically correct or that a live provider and deployed website are reachable; those require separate end-to-end verification.
