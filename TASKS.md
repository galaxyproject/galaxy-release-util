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

1. Go to: https://github.com/galaxyproject/galaxy/pulls, search for:
```
is:open is:pr milestone:<RELEASE_TAG> -label:kind/bug -is:draft
```

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

1. Go to: https://github.com/galaxyproject/galaxy/issues
   
2. Search for: `Publication of Galaxy Release`
 
3. Select and close previous publication issues

### Step 6: Open New Release Publication Issue
Using `galaxy-release-util`, we are now ready to publish the release issue on `GitHub`, which will publicly track the release publication stages using a checklist of items.

1. Make sure that you are in your `galaxy-release-util` virtual environment.

2. Enter your Galaxy root directory:
```bash
cd <GALAXY_ROOT>
```

3. Review the release issue output in the terminal (`--dry-run yes`):
```
galaxy-release-util create-release-issue <RELEASE_TAG> --freeze-date 'YEAR-MONTH-DAY' --release-date 'YEAR-MONTH-DAY' --next-version <NEXT_RELEASE_TAG> --dry-run yes
```

4. Re-run the above command without the `--dry-run` argument to actually open a release publication issue on `GitHub`.

### Step 7: Create Milestone for Future Release
Using the GitHub interface, create a new milestone.

1. Go to https://github.com/galaxyproject/galaxy/milestones
  
2. Click **New milestone** and create a new milestone

3. Note the milestone number from the URL:  
```
https://github.com/galaxyproject/galaxy/milestone/<MILESTONE_NUMBER>
```

5. Edit https://github.com/galaxyproject/galaxy/blob/dev/.github/workflows/maintenance_bot.yaml and update `<MILESTONE_NUMBER>` so new pull requests are tagged with the correct milestone

6. Open a pull request to update the milestone.  
   Example: https://github.com/galaxyproject/galaxy/pull/20946

### Step 8: Are we good to freeze?

Use the following filter to identify PRs without `kind/*` labels and assign the appropriate `kind/*` labels. This helps compile the final list of PRs for the current milestone that must be included in the release by the freeze date.

1. Go to: https://github.com/galaxyproject/galaxy/pulls and search for:
```
is:open is:pr milestone:<RELEASE_TAG> -label:"kind/feature" -label:"kind/bug" -label:"kind/enhancement" -label:"kind/refactoring" -label:dependencies
```

2. Assign proper labels, and milestones to these PRs

### Step 9: Review of Blockers

Write the following message to above channels:

> 📌 We're Frozen!
> Hey everyone!
> As planned, as of today we're officially frozen for <RELEASE_TAG> - no new features or enhancements against the <RELEASE_TAG> milestone after this point.
> We still have <NUMBER_OF_OPEN_PRS> PRs from the freeze list that need to be merged before we can branch. It would be great if folks can review these remaining ones as soon as possible, so we can actually branch. Even if a PR is assigned to someone else, feel free to jump in with a review!
> Link to the remaining PRs: https://github.com/galaxyproject/galaxy/pulls?q=is%3Aopen+is%3Apr+-label%3A%22kind%2Fbug%22+-is%3Adraft+milestone%3A<RELEASE_TAG>

### Step 10: Review Merged PRs

1. Go to: https://github.com/galaxyproject/galaxy/pulls

2. Identify all PRs merged since the last release that are missing the appropriate tag and assign the correct tag. Search for:
```
is:pr is:merged -label:merge sort:merged merged:><YEAR-MONTH-DAY-PREVIOUS-RELEASE> -milestone:<RELEASE_TAG>
```

4. Review all PRs for the new release and update their titles as needed according to the Galaxy contributing guidelines, particularly point 6: https://github.com/galaxyproject/galaxy/blob/dev/CONTRIBUTING.md#how-to-contribute. Search for:
```
is:pr milestone:<RELEASE_TAG>
```

### Step 11: Update Database Revision

1. Switch to your `dev` branch and ensure it is up to date, for example by running:  
```bash
git pull upstream dev
```

2. Run:  
```bash
./manage_db.sh version
```

3. Note the first revision identifier `<DB_REVISION> (gxy) (head)`.

4. Edit `lib/galaxy/model/migrations/dbrevisions.py` and add a new entry:  
```
"<RELEASE_TAG>": "<DB_REVISION>",
```

6. Open a pull request to update the database revision.  
   Example: https://github.com/galaxyproject/galaxy/pull/21017

### Step 12: Merge Previous Release into `dev`

1. Check out the previous release:  
```bash
git checkout release_<PREVIOUS_RELEASE_TAG>
```

2. Ensure the previous release is up to date:  
```bash
git pull upstream release_<PREVIOUS_RELEASE_TAG>
```

3. Check out `dev` and merge the previous release into it:  
```bash
git checkout dev
git merge release_<PREVIOUS_RELEASE_TAG>
git commit -a -m "Merge <PREVIOUS_RELEASE_TAG> into dev"
git push
```

6. Open a pull request against `dev` and merge it.

### Step 13: Create Release Candidate Branches

1. Check out the `dev` branch and pull the latest changes:  
```bash
git checkout dev
git pull upstream dev
```

2. Run the release creation command:  
```bash
make release-create-rc
```

3. This command creates two branches:

   **a. `version-<FUTURE_RELEASE_TAG>.dev`**  
   Title: `Version <FUTURE_RELEASE_TAG>.dev`  
   - Open a pull request **against `dev`**.  
     Example: [https://github.com/galaxyproject/galaxy/pull/21020](https://github.com/galaxyproject/galaxy/pull/21020)  
   - **Note:** Manually verify this step because it:  
     1. may generate the wrong future release number  
     2. adds a client-hash-build file that must be removed

   **b. `version-<RELEASE_TAG>.rc1`**  
   Title: `Update version to <RELEASE_TAG>.rc1`  
   - Open a pull request **against `galaxyproject:release_<RELEASE_TAG>`**.  
     Example: [https://github.com/galaxyproject/galaxy/pull/21019](https://github.com/galaxyproject/galaxy/pull/21019)


   
   
