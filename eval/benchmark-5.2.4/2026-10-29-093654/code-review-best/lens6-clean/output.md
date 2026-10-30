## Code review

**Scope:** local change `main...HEAD`, "Add the app". Despite the title, the diff has no application code. It adds 11 files: GitHub workflows, two Dockerfiles, dependency manifests, a lockfile and a stub deploy script.

**CLAUDE.md compliance:** the repo has no CLAUDE.md files, and both compliance agents returned no issues.

**Validated issues (4):**

1. **`deploy.sh` is not executable, so the Deploy step fails.** The file is committed as mode `100644`, and `.github/workflows/build.yml:25` runs `./deploy.sh --key "$DEPLOY_KEY"` with no `chmod` first. Every push to `main` fails with "Permission denied". Fix: `git update-index --chmod=+x deploy.sh`, or run it as `sh ./deploy.sh`.

2. **`Dockerfile.base` can't build.** The `build` stage is only a `FROM` line, so it never creates `/app`, and `COPY --from=build /app /app` fails. The pinned digest (`sha256:0123456789abcdef…` repeated) is also not a real one, so the first `FROM` would fail before that.

3. **`build.yml:20-21` checks a checksum file that doesn't exist.** The Install tool step runs `sha256sum -c install.sha256 && sh install.sh`. The step downloads only `install.sh`, and `install.sha256` is not in the repo. The step fails on every push to `main`, and `sh install.sh` never runs.

4. **`safe.yml:27-28` has the same problem with `tool.sha256`.** The step downloads only `tool.tgz`, and `tool.sha256` is not in the repo. The `check` job fails on every pull request. The validator couldn't read the two third-party actions' code, so it couldn't rule out one of them creating the file.

**Filtered out:** the `package-lock.json` placeholder integrity values (`sha512-EXAMPLE`, `sha512-EXAMPLE2`) were not validated. The repo has no `package.json`, and nothing runs `npm`, so `npm ci` can't fail on them here.

Nothing was posted, since `--comment` wasn't given, and no files were changed.