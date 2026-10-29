```json
[
  {
    "file": "requirements.txt",
    "line": 2,
    "summary": "`--index-url` pointing at an internal index replaces PyPI for the whole file, so `requests` and `ourlib` both resolve from it. The `--index-url` also sits after `requests`, which is misleading.",
    "failure_scenario": "`pip install -r requirements.txt` fetches every package, including `requests==2.32.3`, from pypi.internal.example. If that index proxies or lets others publish, an attacker can publish a malicious `ourlib` or `requests`. If it does not mirror PyPI, the install fails. Nothing is hash-pinned, because there is no `--require-hashes`. The safer form is `--extra-index-url` with hashes, or a private-only index with namespace control."
  },
  {
    "file": "requirements-dev.txt",
    "line": 1,
    "summary": "A second `--index-url` in the dev requirements file repeats the same dependency-confusion exposure for `ourlib==1.0`, and there are no hashes.",
    "failure_scenario": "`pip install -r requirements-dev.txt` trusts whatever the internal index serves for `ourlib`. With `--extra-index-url` it would instead take the highest version from either index. In either case a compromised or confused index delivers attacker code into dev and CI."
  },
  {
    "file": ".github/workflows/build.yml",
    "line": 20,
    "summary": "The step downloads `install.sh` over the network, then verifies it against `install.sha256`. That checksum file is not in the repo, and if it were fetched from the same origin it would prove nothing.",
    "failure_scenario": "`install.sha256` does not exist in the checkout, so `sha256sum -c` fails and the build always breaks. If someone adds a checksum fetched from tools.example.com, an attacker who controls that host controls both files, and `sh install.sh` runs attacker code in a job that later holds `DEPLOY_KEY`."
  },
  {
    "file": ".github/workflows/build.yml",
    "line": 25,
    "summary": "`DEPLOY_KEY` is passed as a command-line argument (`--key \"$DEPLOY_KEY\"`), and `deploy.sh` never reads it.",
    "failure_scenario": "The key is visible in the process argument list (`ps`) to any process on the runner, including the unverified `install.sh` run earlier in the same job. It can also leak through shell tracing. `deploy.sh` ignores `$@`, so the secret is exposed for no benefit."
  },
  {
    "file": "deploy.sh",
    "line": 4,
    "summary": "`deploy.sh` only echoes \"deploying\". It performs no deployment and ignores the `--key` argument that the workflow passes.",
    "failure_scenario": "The Deploy step reports success on every push to main while nothing is deployed. A green build is therefore misleading, and the key plumbing is dead code."
  },
  {
    "file": "Dockerfile.base",
    "line": 3,
    "summary": "`COPY --from=build /app /app` copies a path that the `build` stage never creates, because that stage is only a bare `FROM`.",
    "failure_scenario": "`docker build -f Dockerfile.base` fails with \"/app: not found\". The pinned digest looks like a placeholder, so it may also fail to resolve. The final image is `scratch` with no runtime."
  },
  {
    "file": "Dockerfile",
    "line": 1,
    "summary": "The image uses an unpinned base tag, runs as root, and runs `COPY . /app` before the dependency install, which defeats layer caching and bakes the whole context into the image.",
    "failure_scenario": "`python:3.12-slim` drifts between builds, so builds are not reproducible. Any change to any file reruns `pip install`. Anything in the build context, including `.git` and local secrets or `.env` files, is copied into the image because there is no `.dockerignore`. The container runs as root. Dockerfile line 3 also installs with no hash pinning."
  },
  {
    "file": "package-lock.json",
    "line": 13,
    "summary": "`our-utils` looks like an internal package but is resolved from the public npm registry. The `integrity` values for both packages are placeholders (`sha512-EXAMPLE`, `sha512-EXAMPLE2`).",
    "failure_scenario": "If `our-utils` is private, anyone can publish that name on public npm, which is a dependency-confusion takeover. `npm ci` fails on the invalid integrity strings. If the strings are not strictly validated, integrity checking is effectively absent."
  },
  {
    "file": ".github/workflows/safe.yml",
    "line": 22,
    "summary": "`lockedorg/tool@v1` is a mutable tag. `actions.lock` records a SHA for it, but GitHub Actions does not read that file, so the pin is never enforced.",
    "failure_scenario": "The owner moves `v1` to a malicious commit, and the workflow runs it while `TOKEN` (`API_TOKEN`) is in scope. The lock file gives a false sense of pinning. The same step block also downloads `tool.tgz` and checks it against `tool.sha256`, which is neither in the repo nor from an independent source."
  },
  {
    "file": ".github/workflows/triage.yml",
    "line": 12,
    "summary": "A `pull_request_target` workflow with write permissions runs a third-party action and checks out the repo with default credentials persisted. `safe-target.yml` does the same.",
    "failure_scenario": "The checkout uses the default `persist-credentials: true`, so the write-scoped token stays in `.git/config` for later steps. The `someorg/labeler` step runs with that token on every PR event, including PRs from forks. If a later edit adds `ref: ${{ github.event.pull_request.head.sha }}`, or the labeler reads PR-controlled files, the token is exposed to untrusted code. The SHA `1111…` also looks like a placeholder that cannot resolve."
  }
]
```