"""A small consumer repository whose manifest and workflows follow every rule `check` enforces.

Every hostile test starts from these bytes and makes one edit, so a green baseline is what makes
each refusal meaningful.
"""

from __future__ import annotations

MANIFEST = """\
schema_version = 1

[lanes.build]
workflows = ["ci.yml"]
paths = ["src/**", "scripts/build.sh"]

[lanes.lint]
workflows = ["ci.yml"]
paths = ["src/**", "scripts/lint.sh"]

[lanes.infra]
workflows = ["matrix.yml"]
paths = ["infra/**"]

[lanes.docs]
workflows = ["docs.yml"]
paths = ["docs/**"]

[gates.infra-gate]
workflow = "matrix.yml"
jobs = { validate = "infra" }

[[fixtures]]
name = "docs only"
files = ["docs/readme.md"]
expect = { build = false, lint = false, infra = false, docs = true }
"""

CI = """\
name: CI
on:
  pull_request:
  push:
    branches: [main]
jobs:
  plan:
    runs-on: ubuntu-latest
    outputs:
      lanes: ${{ steps.plan.outputs.lanes }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - id: plan
        uses: ./actions/ci-lanes
  build:
    needs: plan
    if: ${{ always() && (needs.plan.result != 'success' || fromJSON(needs.plan.outputs.lanes).build != 'false') }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: bash scripts/build.sh src/app.cs
  lint:
    needs: plan
    if: always()
    uses: example/workflows/.github/workflows/lint.yml@0123456789abcdef0123456789abcdef01234567
    with:
      enabled: ${{ needs.plan.result != 'success' || fromJSON(needs.plan.outputs.lanes).lint != 'false' }}
      script: scripts/lint.sh
  secrets:
    runs-on: ubuntu-latest
    steps:
      - run: echo "always on, so it may name README.md and scripts/audit.sh freely"
"""

MATRIX = """\
name: Matrix
on: pull_request
jobs:
  plan:
    runs-on: ubuntu-latest
    outputs:
      lanes: ${{ steps.plan.outputs.lanes }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - id: plan
        uses: ./actions/ci-lanes
  validate:
    needs: plan
    if: ${{ always() && (needs.plan.result != 'success' || fromJSON(needs.plan.outputs.lanes).infra != 'false') }}
    runs-on: ubuntu-latest
    strategy:
      matrix:
        dir: [a, b]
    steps:
      - run: terraform -chdir=infra/modules/${{ matrix.dir }} validate
  infra-gate:
    needs: [plan, validate]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - uses: ./actions/ci-lanes
        with:
          mode: verdict
          gate: infra-gate
          needs: ${{ toJSON(needs) }}
"""

DOCS = """\
name: Docs
on: pull_request
jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - id: relevance
        uses: ./actions/ci-lanes
        with:
          lane: docs
      - if: steps.relevance.outputs.relevant == 'true'
        run: cat docs/readme.md
"""

FILES: dict[str, str] = {
    ".github/ci-lanes.toml": MANIFEST,
    ".github/workflows/ci.yml": CI,
    ".github/workflows/matrix.yml": MATRIX,
    ".github/workflows/docs.yml": DOCS,
    "README.md": "# consumer\n",
    "docs/readme.md": "docs\n",
    "infra/modules/a/main.tf": "# a\n",
    "infra/modules/b/main.tf": "# b\n",
    "scripts/audit.sh": "echo audit\n",
    "scripts/build.sh": "echo build\n",
    "scripts/lint.sh": "echo lint\n",
    "src/app.cs": "class App {}\n",
}
