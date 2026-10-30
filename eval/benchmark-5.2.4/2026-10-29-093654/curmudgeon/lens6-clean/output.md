**CONCERNS** · Counts: 0 Critical, 0 High, 3 Medium, 2 Low

Three blind reviewers and one verifier traced these through the code. Nothing was run, because Bash was denied to the reviewers. The scripted scan reported 0 FAIL, and I changed no project files.

1. **Medium, `build.yml:21` (also `safe.yml:28`), F-5c65c584.** `sha256sum -c install.sha256` checks a file that is never downloaded and isn't in the repo. The install step fails on every push to main, and `safe.yml` fails the same way on every pull request. All 3 reviewers raised it and the verifier confirmed it.
2. **Medium, `Dockerfile.base:3`, F-eea70b7f.** It copies `/app` from a build stage that never creates it, and the pinned digest is a placeholder. The build fails at the pull. All 3 reviewers raised it and the verifier confirmed it.
3. **Medium, `package-lock.json:11` and `:16`, F-b9aefa0d.** The integrity values are placeholders (`sha512-EXAMPLE`), and there is no `package.json`. `npm ci` cannot succeed. 2 of 3 reviewers raised it and the verifier confirmed it.
4. **Low, `deploy.sh:4`, F-970bf915.** It only echoes `deploying`, ignores `--key` and exits 0. The verifier lowered it from Medium because item 1 fails first today. It becomes a false green once item 1 is fixed.
5. **Low, `Dockerfile:1`, F-70c4cc26.** `python:3.12-slim` is a floating tag, while `Dockerfile.base` pins by digest.

There are also seven Nits, listed but not counted. They include running as root with no `.dockerignore`, the deploy key passed as a command-line argument, and `our-utils` resolving from public npm. The full teardown is in `.critic/last-review.md`. It also lists six findings the script dropped, because only one reviewer raised each.

- **Held up:** untrusted PR text reaches the shell only through `env:`, and the two `pull_request_target` workflows check out the base ref and run no PR code.
- **Not checked:** `npm ci`, `docker build` and the workflows were traced, not run. I did not confirm the repo's visibility. That matters for the dropped `triage.yml` `contents: read` point.
- **Skipped:** the spot-check and the outside-reviewer offer, because this ran unattended. The variant hunt had nothing to start from, since no Critical or High finding survived.

To fix them, run `/curmudgeon:review fix` for all five, or `/curmudgeon:fix patch [id]` for one.