# Galaxy Release Manager Tasks

This document provides a step-by-step guide for managing Galaxy releases. It outlines the key responsibilities of the release manager, from determining the freeze date to preparing and executing the release. Each step includes practical instructions, recommended commands, and communication guidelines to ensure a smooth and coordinated release process.

## Tasks

### Step 1: Determine Freeze and Release Date

Discuss and agree on an appropriate freeze date (FREEZE_DATE) and anticipated release date (RELEASE_DATE) with the team during a dev meeting.

### Step 2: Announce Freeze Meeting

Two weeks before the actual freeze, we announce the freeze meeting for the upcoming week.

1. Send the following message:

>🗓️ Freeze Meeting on <FREEZE_MEETING_DATE>
>
>We will meet on <FREEZE_MEETING_DATE> for the Freeze Meeting, one week before the actual freeze. We will review open PRs, decide what will be included in the <RELEASE_TAG> release, and assign reviewers to ensure merges are completed by the freeze date. If you have outstanding PRs, please make sure they are set to ready-for-review before the meeting.

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
git pull
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

### Step 5: Close Previous Release Publication Issues
We ensure that all previous release publication issues are closed before publishing a new one.

1. Go to: [https://github.com/galaxyproject/galaxy/issues](https://github.com/galaxyproject/galaxy/issues)
   
2. Search for: `Publication of Galaxy Release`
 
3. Select and close previous publication issues

### Step 6: Open Release Publication Issue
Using `galaxy-release-util`, we are now ready to publish the release issue on `GitHub`, which will publicly track the release publication stages using a checklist of items.

1. Make sure that you are in your `galaxy-release-util` virtual environment.

2. Enter your Galaxy root directory:
```bash
cd <GALAXY_ROOT>
```

3. Review the release issue output in the terminal (`--dry-run`): `galaxy-release-util create-release-issue <RELEASE_TAG> --freeze-date 'YEAR-MONTH-DAY' --next-version <NEXT_RELEASE_TAG> --dry-run y --release-date 'YEAR-MONTH-DAY'`

5. Re-run the above command without the `--dry-run` argument to actually open a release publication issue on `GitHub`.

### Step 7: Are we good to freeze?

Use the following filter to identify PRs without `kind/*` labels and assign the appropriate `kind/*` labels. This helps compile the final list of PRs for the current milestone that must be included in the release by the freeze date.

1. Go to: [https://github.com/galaxyproject/galaxy/pulls](https://github.com/galaxyproject/galaxy/pulls)  
2. Search for: `is:open is:pr milestone:<RELEASE_TAG> -label:"kind/feature" -label:"kind/bug" -label:"kind/enhancement" -label:"kind/refactoring" -label:dependencies`
3. Assign proper labels, and milestones to these PRs
