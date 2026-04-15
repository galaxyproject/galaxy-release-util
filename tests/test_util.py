import pytest

from galaxy_release_util.util import escape_rst_inline


@pytest.mark.parametrize(
    "input_text, expected",
    [
        ("simple title", "simple title"),
        ("has *bold* text", r"has \*bold\* text"),
        ("has `code` here", r"has \`code\` here"),
        ("pipe|separated", r"pipe\|separated"),
        ("backslash\\present", r"backslash\\present"),
        ("mixed *bold* and `code`", r"mixed \*bold\* and \`code\`"),
        ("no special chars", "no special chars"),
        ("", ""),
        ("***triple***", r"\*\*\*triple\*\*\*"),
    ],
)
def test_escape_rst_inline(input_text, expected):
    assert escape_rst_inline(input_text) == expected
