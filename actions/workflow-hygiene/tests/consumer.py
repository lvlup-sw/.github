"""A small consumer repository whose workflows follow both rules.

Every hostile test starts from these bytes and makes one edit, so a green baseline is what makes
each refusal meaningful. It covers each shape the rules must accept: the shared workflow-level
concurrency block, job-level concurrency on every job, a reusable-workflow call with no timeout, a
non-pull-request workflow with no concurrency, a ``.yaml`` file, and one exemption in use.
"""

from __future__ import annotations

CI = ".github/workflows/ci.yml"
GATE = ".github/workflows/gate.yaml"
REUSABLE = ".github/workflows/reusable.yml"
NIGHTLY = ".github/workflows/nightly.yml"
CONFIG = ".github/workflow-hygiene.toml"

SHARED_CONCURRENCY = """\
concurrency:
  group: ${{ github.workflow }}-${{ github.event_name == 'pull_request' && github.event.pull_request.number || github.run_id }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
"""

FILES: dict[str, str] = {
    CI: f"""\
name: CI

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
  push:
    branches: [main]

{SHARED_CONCURRENCY}
permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - run: echo build
  test:
    needs: build
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - run: echo test
  lint:
    uses: ./.github/workflows/reusable.yml
""",
    GATE: """\
name: Gate

on: [pull_request, workflow_dispatch]

jobs:
  bench:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    concurrency:
      group: bench-${{ github.ref }}
      cancel-in-progress: true
    steps:
      - run: echo bench
  report:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    concurrency:
      group: report-${{ github.ref }}
      cancel-in-progress: 'true'
    steps:
      - run: echo report
""",
    REUSABLE: """\
name: Reusable lint

on:
  workflow_call:

jobs:
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - run: echo lint
""",
    NIGHTLY: """\
name: Nightly

on:
  schedule:
    - cron: '0 6 * * *'

jobs:
  soak:
    runs-on: ubuntu-latest
    steps:
      - run: echo soak
""",
    CONFIG: """\
[exempt]
"nightly.yml:soak" = "the soak test is bounded by its own harness deadline"
""",
    ".github/workflows/README.md": "Not a workflow; the scan must ignore it.\n",
}
