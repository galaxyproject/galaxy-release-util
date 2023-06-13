import re
from typing import List

from github.PullRequest import PullRequest

PROJECT_OWNER = "galaxyproject"
PROJECT_NAME = "galaxy"
PROJECT_URL = f"https://github.com/{PROJECT_OWNER}/{PROJECT_NAME}"
PROJECT_API = f"https://api.github.com/repos/{PROJECT_OWNER}/{PROJECT_NAME}/"

GROUPED_TAGS = dict(
    [
        ("area/visualizations", "viz"),
        ("area/datatypes", "datatypes"),
        ("area/tools", "tools"),
        ("area/workflows", "workflows"),
        ("area/client", "ui"),
        ("area/jobs", "jobs"),
        ("area/admin", "admin"),
    ]
)


def _pr_to_str(pr):
    if isinstance(pr, str):
        return pr
    return f"PR #{pr.number} ({pr.title}) {pr.html_url}"


def _text_target(pull_request: PullRequest, skip_merge=True):
    pr_number = pull_request.number
    labels = [label.name.lower() for label in pull_request.labels]
    is_bug = is_enhancement = is_feature = is_minor = is_major = is_merge = is_small_enhancement = False
    if len(labels) == 0:
        print(f"No labels found for {pr_number}")
        return None
    for label_name in labels:
        if label_name == "minor":
            is_minor = True
        elif label_name == "major":
            is_major = True
        elif label_name == "merge":
            is_merge = True
        elif label_name == "kind/bug":
            is_bug = True
        elif label_name == "kind/feature":
            is_feature = True
        elif label_name == "kind/enhancement":
            is_enhancement = True
        elif label_name in ["kind/testing", "kind/refactoring"]:
            is_small_enhancement = True
        elif label_name == "procedures":
            # Treat procedures as an implicit enhancement.
            is_enhancement = True

    is_some_kind_of_enhancement = is_enhancement or is_feature or is_small_enhancement

    if not (is_bug or is_some_kind_of_enhancement or is_minor or is_merge):
        print(f"No 'kind/*' or 'minor' or 'merge' or 'procedures' label found for {_pr_to_str(pull_request)}")
        text_target = None

    if is_minor or is_merge and skip_merge:
        return

    if is_some_kind_of_enhancement and is_major:
        text_target = "major_feature"
    elif is_feature:
        text_target = "feature"
    elif is_enhancement:
        for label, tag in GROUPED_TAGS.items():
            if label in labels:
                text_target = f"enhancement_tag_{tag}"
                break
        else:
            text_target = "enhancement"
    elif is_some_kind_of_enhancement:
        text_target = "small_enhancement"
    elif is_major:
        text_target = "major_bug"
    elif is_bug:
        for label, tag in GROUPED_TAGS.items():
            if label in labels:
                text_target = f"bug_tag_{tag}"
                break
        else:
            text_target = "bug"
    else:
        print(f"Logic problem, cannot determine section for {_pr_to_str(pull_request)}")
        text_target = None
    if text_target:
        text_target += "\n"
    return text_target


def _pr_to_labels(pr: PullRequest) -> List[str]:
    labels = [label.name.lower() for label in pr.labels]
    return labels


def strip_release(message):
    return re.sub(r"^\s*\[.*\]\s*", r"", message)
