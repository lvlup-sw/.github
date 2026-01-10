# lvlup-sw Organization Defaults

This repository contains organization-wide community health files, reusable workflows, and templates for all lvlup-sw repositories.

## What's Included

### Issue Templates (`ISSUE_TEMPLATE/`)
Default issue templates applied to all repos without their own templates:
- **Bug Report** - Report something that isn't working
- **Feature Request** - Suggest a new feature

### Labels (`labels-base.yml`)
Standard label definitions for consistent issue/PR organization:

| Category | Labels |
|----------|--------|
| **Type** | `type:bug`, `type:feature`, `type:docs`, `type:chore`, `type:question` |
| **Status** | `status:triage`, `status:blocked`, `status:stale` |
| **Priority** | `priority:high`, `priority:low` |

### Reusable Workflows (`.github/workflows/`)

#### Label Sync (`label-sync.yml`)
Automatically syncs labels from `labels.yml` to GitHub. Call from your repo:

```yaml
jobs:
  label-sync:
    uses: lvlup-sw/.github/.github/workflows/label-sync.yml@main
    secrets: inherit
```

### Workflow Templates (`workflow-templates/`)

#### Project Automation
Complete automation workflow with:
- **Label sync** - Syncs labels when `labels.yml` changes
- **Auto-triage** - Labels new issues based on content patterns
- **Auto-assign** - Assigns PR author as assignee
- **Project sync** - Adds issues/PRs to org project board (project 3)
- **Stale management** - Marks/closes inactive issues after 60 days
- **Renovate auto-merge** - Auto-merges Renovate dependency PRs
- **Release automation** - Generates changelog and creates releases from tags

### Rulesets (`rulesets/default.json`)
Reference template for branch protection. Copy to your repo and apply via GitHub UI or API.

## Usage

### For New Repos

1. **Copy labels**: Copy `labels-base.yml` to `.github/labels.yml`
2. **Add scopes**: Add domain-specific `scope:*` labels for your project
3. **Copy workflow**: Copy `workflow-templates/project-automation.yml` to `.github/workflows/`
4. **Customize**: Update scope detection patterns in auto-triage job
5. **Set secret**: Ensure `PROJECT_TOKEN` secret is configured for project sync

### For Existing Repos

Issue templates from this repo automatically apply to repos without their own templates.

To add label sync to an existing repo, add this to your workflow:

```yaml
on:
  push:
    branches: [main]
    paths:
      - '.github/labels.yml'

jobs:
  label-sync:
    uses: lvlup-sw/.github/.github/workflows/label-sync.yml@main
    secrets: inherit
```

### Required Secrets

| Secret | Purpose |
|--------|---------|
| `PROJECT_TOKEN` | PAT with `project` scope for adding items to org projects |

## Project Configuration

All repos should use **Project 3** for issue/PR tracking. Set in your workflow:

```yaml
env:
  PROJECT_NUMBER: 3
```
