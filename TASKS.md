# Galaxy Release Manager Tasks

This document provides a step by step guide for managing Galaxy releases. It outlines the responsibilities of the release manager from determining the freeze date to preparing and executing the release. Each step includes concrete actions, commands, and communication guidance to ensure a predictable and coordinated release process.

## Terminology

* RELEASE_TAG: the release being prepared, for example 26.0
* PREVIOUS_RELEASE_TAG: the last published release, for example 25.1
* NEXT_RELEASE_TAG: the next planned release, for example 26.1
* FREEZE_DATE: the date the release branch is frozen, for example 2026-01-27
* RELEASE_DATE: the anticipated publication date, for example 2026-02-17

## Tasks

### Step 1: Determine Freeze and Release Dates

Discuss and agree on a tentative freeze date (FREEZE_DATE) and anticipated release date (RELEASE_DATE) with the team during a dev meeting. These dates are provisional until confirmed at the Freeze Meeting.

---

### Step 2: Announce Freeze Meeting

Two weeks before the planned freeze, announce the Freeze Meeting for the following week. The meeting is held one week before the actual freeze.

Send the following message:

> 🗓️ Freeze Meeting on <FREEZE_MEETING_DATE>
>
> We will meet on <FREEZE_MEETING_DATE> for the Freeze Meeting, one week before the actual freeze. We will review open PRs, decide what will be included in the <RELEASE_TAG> release, and assign reviewers to ensure merges are completed by the freeze date. If you have outstanding PRs, please make sure they are set to ready for review before the meeting.

Send this message to at least the following channels:

* [https://matrix.to/#/#galaxyproject_ui-ux:gitter.im](https://matrix.to/#/#galaxyproject_ui-ux:gitter.im)
* [https://matrix.to/#/#galaxyproject_backend:gitter.im](https://matrix.to/#/#galaxyproject_backend:gitter.im)

---

### Step 3: Install Galaxy Release Utility

Much of the release process is automated using `galaxy-release-util`. Ensure it is installed and up to date.

1. Clone the repository if not already present:

```bash
git clone https://github.com/galaxyproject/galaxy-release-util
```

2. Update to the latest version:

```bash
cd galaxy-release-util
git pull
```

3. Install and activate the virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

4. Verify that the correct executable is used:

```bash
which galaxy-release-util
```

All subsequent uses of `galaxy-release-util` are expected to be run from this virtual environment.

---

### Step 4: Close Previous Release Publication Issues

Ensure all previous release publication issues are closed before starting a new release to avoid ambiguity about which checklist corresponds to the active release.

1. Go to [https://github.com/galaxyproject/galaxy/issues](https://github.com/galaxyproject/galaxy/issues)

2. Search for: `Publication of Galaxy Release`

3. Close any previous publication issues that are still open

---

### Step 5: Create and Configure a GitHub Authentication Token

This step enables authenticated access for `galaxy-release-util` to create release issues, milestones, and related metadata on GitHub. Classic tokens are required because fine grained tokens do not currently provide the necessary permissions.

1. Create a classic GitHub personal access token:

   * Navigate to [https://github.com](https://github.com)
   * Open your profile menu
   * Select Settings
   * Select Developer settings
   * Select Personal access tokens
   * Select Tokens (classic)
   * Click Generate new token
   * Select Generate new token (classic)
   * Add a descriptive note indicating Galaxy release management
   * Enable the following scopes:

     * `repo`
     * `write:packages`
     * `delete:packages`
     * `admin:repo_hook`
   * Generate the token

2. Export the token in your shell environment:

```bash
export GITHUB_AUTH=<TOKEN>
```

3. Ensure the variable is available in the same shell session where `galaxy-release-util` will be executed.

---

### Step 6: Create Release Config YAML

All release metadata is defined in a single YAML config file. Once committed, all `galaxy-release-util` commands load it automatically from the default path given a release version.

1. Change to your Galaxy root directory:

```bash
cd <GALAXY_ROOT>
```

2. Create the release config file at `doc/source/releases/release_<RELEASE_TAG>.yml`:

```yaml
current-version: "<RELEASE_TAG>"
previous-version: "<PREVIOUS_RELEASE_TAG>"
freeze-date: "<FREEZE_DATE>"
release-date: "<RELEASE_DATE>"
```

All fields are required. Two optional fields, `owner` and `repo`, default to `"galaxyproject"` and `"galaxy"` respectively. Override them only when working with a private or forked repository. The `next-version` value is provided via the `--next-version` CLI flag on commands that require it (e.g. `create-release-issue`, `create-changelog`).

3. Commit this file to the repository so it is available for all subsequent release commands.

---

### Step 7: Open New Release Publication Issue

Using `galaxy-release-util`, create the release publication issue that tracks all publication tasks for the current release.

1. Ensure you are in the `galaxy-release-util` virtual environment.

2. Change to your Galaxy root directory:

```bash
cd <GALAXY_ROOT>
```

3. Review the generated release issue content:

```bash
galaxy-release-util create-release-issue <RELEASE_TAG> --galaxy-root . --next-version <NEXT_RELEASE_TAG> --dry-run
```

To use a config file at a non-default location, add `--release-config /path/to/config.yml`.

4. Re run the command without `--dry-run` to open the issue on GitHub.

---

### Step 8: Create Milestone for Next Release

Create a milestone for the next release so new pull requests are tagged correctly.

1. Go to [https://github.com/galaxyproject/galaxy/milestones](https://github.com/galaxyproject/galaxy/milestones)

2. Click New milestone and create a milestone for <NEXT_RELEASE_TAG>

3. Note the milestone number from the URL:

```
https://github.com/galaxyproject/galaxy/milestone/<MILESTONE_NUMBER>
```

4. Edit [https://github.com/galaxyproject/galaxy/blob/dev/.github/workflows/maintenance_bot.yaml](https://github.com/galaxyproject/galaxy/blob/dev/.github/workflows/maintenance_bot.yaml) and update `<MILESTONE_NUMBER>` so new pull requests are assigned to the correct milestone

5. Open a pull request to apply the change

---

### Step 9: Freeze Meeting

One week before the freeze, hold the Freeze Meeting, usually during a weekly dev meeting. In this meeting, review open pull requests, decide what will be included in the <RELEASE_TAG> release, and assign reviewers to ensure merges complete before the freeze. Milestone decisions made here are binding for the freeze.

To list pull requests for discussion:

1. Go to [https://github.com/galaxyproject/galaxy/pulls](https://github.com/galaxyproject/galaxy/pulls) and search for:

```
is:open is:pr milestone:<RELEASE_TAG> -label:kind/bug -is:draft
```

---

### Step 10: Final Pre Freeze Milestone and Label Audit

Before freezing, ensure all pull requests in the milestone have appropriate `kind/*` labels and correct milestone assignment.

1. Go to [https://github.com/galaxyproject/galaxy/pulls](https://github.com/galaxyproject/galaxy/pulls) and search for:

```
is:open is:pr milestone:<RELEASE_TAG> -label:"kind/feature" -label:"kind/bug" -label:"kind/enhancement" -label:"kind/refactoring" -label:dependencies
```

2. Assign appropriate labels and milestones to these pull requests

---

### Step 11: Confirm and Announce Freeze

After completing the audit, the release manager confirms the freeze and announces it.

Send the following message:

> 📌 We are now frozen for <RELEASE_TAG>
>
> As of today, we are officially frozen for <RELEASE_TAG>. No new features or enhancements should be added to the <RELEASE_TAG> milestone after this point.
> We still have <NUMBER_OF_OPEN_PRS> pull requests from the freeze list that must be merged before we can branch. Reviews are appreciated so we can proceed with branching.
> Remaining PRs: https://github.com/galaxyproject/galaxy/pulls?q=is%3Aopen+is%3Apr+-label%3A%22kind%2Fbug%22+-is%3Adraft+milestone%3A<RELEASE_TAG>

---

### Step 12: Review Merged Pull Requests

Ensure all merged pull requests for the release are correctly labeled and titled to support accurate release notes.

1. Identify merged pull requests missing a milestone:

```
is:pr is:merged -label:merge sort:merged merged:><YEAR-MONTH-DAY-PREVIOUS-RELEASE> -milestone:<RELEASE_TAG>
```

2. Assign the correct milestone to these pull requests

3. Review titles of all pull requests in the milestone and adjust them conservatively to match Galaxy contribution guidelines

---

### Step 13: Update Database Revision

Update the database revision mapping for the release. This change must land before branching.

1. Ensure `dev` is up to date:

```bash
git pull upstream dev
```

2. Run:

```bash
./manage_db.sh version
```

3. Note the revision identifier marked as head

4. Add the mapping to `lib/galaxy/model/migrations/dbrevisions.py`:

```
"<RELEASE_TAG>": "<DB_REVISION>",
```

5. Open and merge a pull request with this change

---

### Step 14: Merge Previous Release into dev

Merge the previous release branch into `dev` to ensure all backported fixes are present.

1. Check out and update the previous release:

```bash
git checkout release_<PREVIOUS_RELEASE_TAG>
git pull upstream release_<PREVIOUS_RELEASE_TAG>
```

2. Merge into dev:

```bash
git checkout dev
git merge release_<PREVIOUS_RELEASE_TAG>
git commit -a -m "Merge <PREVIOUS_RELEASE_TAG> into dev"
git push
```

3. Open and merge the resulting pull request

---

### Step 15: Create Release Candidate Branches

Create release candidate and next dev version branches.

1. Update dev:

```bash
git checkout dev
git pull upstream dev
```

2. Run:

```bash
source .venv/bin/activate
make release-create-rc
```

This creates two branches:

a. `version-<NEXT_RELEASE_TAG>.dev`

* Title: Version <NEXT_RELEASE_TAG>.dev
* Open a pull request against `dev`
* Verify the future version number and remove any generated client hash build artifacts if present

b. `version-<RELEASE_TAG>.rc1`

* Title: Update version to <RELEASE_TAG>.rc1
* Open a pull request against galaxyproject:release_<RELEASE_TAG>.
* Example: https://github.com/galaxyproject/galaxy/pull/21019

Note: These steps may silently fail without producing any branches. Inspect `cat packages/app/make-dist.log` if branches were not created.

---

### Step 16: Create a new GitHub label

* Navigate to https://github.com/galaxyproject/galaxy/issues
* Click on `Labels` and `New label`
* Create a new label: `release-testing-<RELEASE_TAG>`
* Use this label to tag all release testing PRs

---

### Step 17: Announce Branching

Send the following message:

> 🌱 Branched <RELEASE_TAG>
>
> The <RELEASE_TAG> release branch has been created.

Send this message to at least the following channels:

* [https://matrix.to/#/#galaxyproject_ui-ux:gitter.im](https://matrix.to/#/#galaxyproject_ui-ux:gitter.im)
* [https://matrix.to/#/#galaxyproject_backend:gitter.im](https://matrix.to/#/#galaxyproject_backend:gitter.im)

---

### Step 18: Assemble Testing Team

Reach out per email to assemble the testing team for the upcoming release:

>**Galaxy <RELEASE_TAG> Release Testing**
>
>Hi,
>
>I am organizing testing for the upcoming Galaxy release and would like to ask whether you would be available to participate.
>
>**Testing window:**
>**<DAY_NAME> <MONTH_NAME> <DAY_COUNT>** through **<DAY_NAME> <MONTH_NAME> <DAY_COUNT>**
>
>**Time commitment:**
>Approximately 1-2 hours per day. Testing consists of working through as many assigned PRs as time permits. There will be one short kick off meeting immediately before testing begins.
>
>**What release testing involves:**
>Release testing focuses on validating Galaxy GitHub pull requests. Each PR represents either a new feature, an enhancement, or a bug fix. Testing means exercising the changes as a user would and verifying that they behave correctly and do not introduce regressions. A curated list of PRs will be provided, and detailed guidance on the testing workflow and PR selection will be covered in the kick off meeting.
>
>I will be available throughout the testing period, and the galaxyproject/release-testing channel on Element will be used for coordination and questions.
>
>If you are able to participate, I will follow up with concrete details.
>
>Thanks!

---

### Step 19: Continue with Release Issue
