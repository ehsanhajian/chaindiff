from chaindiff.versions import parse_version, tag_is_prerelease


def test_padding_and_stable_suffix_compare_equal():
    assert parse_version("v1.2") == parse_version("1.2.0") == parse_version("v1.2.0-stable")


def test_numeric_order_is_not_lexical():
    assert parse_version("1.2.9") < parse_version("1.2.10")


def test_prerelease_orders_before_the_final_release():
    assert parse_version("v8.3.0-alpha.1") < parse_version("v8.3.0-rc.2")
    assert parse_version("v8.3.0-rc.2") < parse_version("v8.3.0-rc.10")
    assert parse_version("v8.3.0-rc.10") < parse_version("v8.3.0")
    assert parse_version("2.0.0-rc2") < parse_version("2.0.0")


def test_unparsable_tags_are_rejected():
    assert parse_version("nightly") is None
    assert parse_version("zkvm-guests-2.1.0-unstable-5c2a2768") is None
    assert parse_version("v2022.10.01") is None


def test_prerelease_words_are_detected():
    assert tag_is_prerelease("v8.3.0-rc.0")
    assert tag_is_prerelease("2.0.0-rc2")
    assert not tag_is_prerelease("v1.17.7")
    assert not tag_is_prerelease("v1.10.17-stable")
