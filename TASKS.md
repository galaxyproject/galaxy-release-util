# Galaxy Release Manager Tasks

This document provides a step-by-step guide for managing Galaxy releases. It outlines the key responsibilities of the release manager, from determining the freeze date to preparing and executing the release. Each step includes practical instructions, recommended commands, and communication guidelines to ensure a smooth and coordinated release process.

## Tasks

### Step 1: Determine Freeze Date

Discuss and agree on an appropriate freeze date (DATE_OF_FREEZE_MEETING) with the team during a dev meeting.

### Step 2: Announce Freeze Meeting

Two weeks before the actual freeze, we announce the freeze meeting for the upcoming week.

1. Send the following message:

>🗓️ Freeze Meeting on <DATE_OF_FREEZE_MEETING>
>
>We will meet on <DATE_OF_FREEZE_MEETING> for the Freeze Meeting, one week before the actual freeze. We will review open PRs, decide what will be included in the <RELEASE_TAG> release, and assign reviewers to ensure merges are completed by the freeze date. If you have outstanding PRs, please make sure they are set to ready-for-review before the meeting.

2. To these channels:

- https://matrix.to/#/#galaxyproject_ui-ux:gitter.im
- https://matrix.to/#/#galaxyproject_backend:gitter.im
- ...


### Step 3: The Freeze Meeting
One week before the freeze, we hold the Freeze Meeting, usually during a weekly dev meeting. In this meeting, we review open PRs, decide what will be included in the <RELEASE_TAG> release, and assign reviewers to ensure PRs are merged by the freeze date. Focus on non-draft, non-bug PRs for this discussion. 

To list all PRs for discussion:

1. Go to: [https://github.com/galaxyproject/galaxy/pulls](https://github.com/galaxyproject/galaxy/pulls)  
2. Search for: `is:open is:pr milestone:<RELEASE_TAG> -label:kind/bug -is:draft`

### Step 4: Install Galaxy Release Utility
Much of the release process has been automated with `galaxy-release-util`. In the following section, we show how to install it and ensure that your installed version is up-to-date.

1. If not already cloned:

```bash
git clone https://github.com/galaxyproject/galaxy-release-util
```

2. Update with latest changes:

```bash
cd galaxy-release-util
git fetch upstream
```

3. Install and activate:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

4. Verify version:

Use the `which` command to confirm that the version of `galaxy-release-util` being used is the one installed in the your virtual environment.

```bash
which galaxy-release-util
```
