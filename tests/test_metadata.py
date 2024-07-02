from galaxy_release_util.metadata import strip_release


def test_strip_release():
    """Verify that the first occurance of [*] is stripped out."""
    assert strip_release("foo") == "foo"
    assert strip_release("[1]foo") == "foo"
    assert strip_release("[1.2.3]foo") == "foo"
    assert strip_release("[]foo") == "foo"
    assert strip_release("[][]foo") == "[]foo"
    assert strip_release("foo[]") == "foo[]"
    assert strip_release("[]foo[]") == "foo[]"
    assert strip_release("foo[bar]") == "foo[bar]"
    assert strip_release("foo[]baz") == "foo[]baz"
    assert strip_release("foo[bar]baz") == "foo[bar]baz"
