# lvlup-sw Organization Defaults

This repository contains organization-wide community health files and templates for all lvlup-sw repositories.

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

Each repo should copy `labels-base.yml` to `.github/labels.yml`, add domain-specific `scope:*` labels, then sync:

```bash
gh label sync --force
```

### Rulesets (`rulesets/default.json`)
Reference template for branch protection. Copy to your repo and apply via GitHub UI or API.

## Usage

### For New Repos

1. Copy `labels-base.yml` to `.github/labels.yml`
2. Add domain-specific `scope:*` labels
3. Run `gh label sync --force`
4. Copy `rulesets/default.json` if needed

### For Existing Repos

Issue templates from this repo automatically apply to repos without their own templates.
