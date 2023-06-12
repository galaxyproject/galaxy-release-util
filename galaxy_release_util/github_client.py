import json
import os

from github import Github


def github_client() -> Github:
    """Search environment for github access token and produce client object.

    Easiest thing to do is just to set an environment variable GITHUB_AUTH to
    your personal access token (
    https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token
    ). Alternatively, this can be placed into a json file in ~/.github.json in a
    map keyed on login_or_token.
    """
    auth = os.environ.get("GITHUB_AUTH")
    if auth is not None:
        return Github(auth)
    else:
        github_json_path = os.path.expanduser("~/.github.json")
        if not os.path.exists(github_json_path):
            return Github(None)
        with open(github_json_path) as fh:
            github_json_dict = json.load(fh)
        return Github(**github_json_dict)
