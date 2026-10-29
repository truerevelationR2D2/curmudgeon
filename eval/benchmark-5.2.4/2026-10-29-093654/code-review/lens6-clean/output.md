## Code review

I read the diff myself (`git diff main...HEAD`: 11 new files, one commit, and `main` is empty) and did not launch sub-agents. There is no `CLAUDE.md` in the repo, so I checked bugs only.

### 1. `deploy.sh` is committed without the executable bit
`.github/workflows/build.yml`, "Deploy" step: `run: ./deploy.sh --key "$DEPLOY_KEY"`.

`git diff` shows `deploy.sh` as `new file mode 100644`, so the checked-out file isn't executable. The step fails with `Permission denied` every time it runs. Either `chmod +x` and commit the mode, or call it as `sh ./deploy.sh`.

### 2. The checksum files the workflows verify against are not in the repo
- **`build.yml`, "Install tool":** `sha256sum -c install.sha256 && sh install.sh`. No `install.sha256` exists in the tree, and the step never downloads one. `sha256sum -c` fails with "No such file", so the install and everything after it, including Deploy, never run.
- **`safe.yml`, "Download and check":** `sha256sum -c tool.sha256` has the same problem. `tool.sha256` is absent, so the step always fails.

In both steps the check can never pass, so the pinning meant to protect the download does nothing. Commit the files with the digests pinned in-repo, or write the digest inline, for example `echo "<sha>  tool.tgz" | sha256sum -c -`.

No other issues met the high-signal bar. I left out the other items because they are design or policy choices rather than certain defects:
- The `--index-url` lines in `requirements.txt` and `requirements-dev.txt`.
- The `Dockerfile` base image, which isn't pinned by digest.
- `DEPLOY_KEY` passed as a command-line argument.