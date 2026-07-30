# Galaxy Release Manager Tasks

This document provides a step by step guide for preparing a Galaxy release. It covers all steps up to and including the creation of the release publication issue. Once the issue is created, all subsequent steps are tracked as checkboxes in the issue itself, making it the single source of truth for the release process.

## Terminology

* RELEASE_TAG: the release being prepared, for example 26.0
* PREVIOUS_RELEASE_TAG: the last published release, for example 25.1
* NEXT_RELEASE_TAG: the next planned release, for example 26.1
* FREEZE_DATE: the date the release branch is frozen, for example 2026-01-27
* RELEASE_DATE: the anticipated publication date, for example 2026-02-17

## Tasks

### Step 1: Determine Freeze and Release Dates

Discuss and agree on a tentative freeze date (FREEZE_DATE) and anticipated release date (RELEASE_DATE) with the team during a dev meeting. These dates are provisional until confirmed at the Freeze Meeting.

RELEASE_DATE is recorded as the due date of the release milestone in Step 6, which is where `galaxy-release-util` reads it from. Whenever the date moves, update the milestone; nothing else needs changing.

---

### Step 2: Announce Freeze Meeting

Two weeks before the planned freeze, announce the Freeze Meeting for the following week. The meeting is held one week before the actual freeze.

Send the following message:

> Freeze Meeting on <FREEZE_MEETING_DATE>
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

### Step 6: Create the GitHub Milestone

GitHub milestones are the source of truth for release metadata. `galaxy-release-util` reads them to work out:

* RELEASE_DATE, from the due date of the milestone named after RELEASE_TAG
* PREVIOUS_RELEASE_TAG, the newest milestone preceding RELEASE_TAG
* NEXT_RELEASE_TAG, the oldest milestone following RELEASE_TAG

So the only setup required is a [milestone](https://github.com/galaxyproject/galaxy/milestones) titled `<RELEASE_TAG>` with its due date set to RELEASE_DATE. Nothing has to be committed to the Galaxy repository, and no command needs the dates passed on the command line.

Open and closed milestones are both read, so PREVIOUS_RELEASE_TAG resolves from an already-closed milestone and the release notes can still be regenerated after RELEASE_TAG's own milestone is closed.

Any value can still be overridden with a flag, for example `--release-date 2026-02-17` or `--next-version 26.2`. FREEZE_DATE is not recorded anywhere on GitHub, so `create-release-issue` takes it as `--freeze-date`.

If GitHub cannot be reached, commands print a warning rather than failing: NEXT_RELEASE_TAG falls back to the next minor version and PREVIOUS_RELEASE_TAG to the newest release under `doc/source/releases`. RELEASE_DATE has no fallback, so a command that needs it will tell you to pass `--release-date`.

#### Working against a fork

Commands read `galaxyproject/galaxy` by default. Pass `--owner` and `--repo` to point them at a fork or private repository; this also decides which milestones are read:

```bash
galaxy-release-util create-changelog <RELEASE_TAG> --owner <OWNER> --repo <REPO>
```

---

### Step 7: Open New Release Publication Issue

Using `galaxy-release-util`, create the release publication issue that tracks all remaining release tasks.

1. Ensure you are in the `galaxy-release-util` virtual environment.

2. Change to your Galaxy root directory:

```bash
cd <GALAXY_ROOT>
```

3. Review the generated release issue content:

```bash
galaxy-release-util create-release-issue <RELEASE_TAG> --freeze-date <FREEZE_DATE> --dry-run
```

Everything else is read from the milestones.

4. Re run the command without `--dry-run` to open the issue on GitHub.

All subsequent release steps are tracked as checkboxes in the publication issue.
