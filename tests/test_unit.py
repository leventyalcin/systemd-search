import pytest
import systemd_search as s


# ---------------------------------------------------------------------------
# parse_cat_output
# ---------------------------------------------------------------------------

CAT_SINGLE_FILE = """\
# /etc/systemd/system/foo.service
[Unit]
Description=Foo

[Service]
ExecStart=/bin/true

[X-Labels]
Project=myapp
Domain=foo
"""

CAT_TWO_FILES = """\
# /etc/systemd/system/foo.service
[Unit]
Description=Foo

[X-Labels]
Project=myapp
Domain=foo

# /etc/systemd/system/foo.service.d/override.conf
[X-Labels]
Domain=bar
Extra=yes
"""

CAT_NO_CUSTOM_SECTION = """\
# /etc/systemd/system/plain.service
[Unit]
Description=Plain

[Service]
ExecStart=/bin/true
"""

CAT_EMPTY = ""


class TestParseCatOutput:
    def test_parses_standard_sections(self):
        result = s.parse_cat_output(CAT_SINGLE_FILE)
        assert result["Unit"]["Description"] == "Foo"
        assert result["Service"]["ExecStart"] == "/bin/true"

    def test_parses_x_section(self):
        result = s.parse_cat_output(CAT_SINGLE_FILE)
        assert result["X-Labels"]["Project"] == "myapp"
        assert result["X-Labels"]["Domain"] == "foo"

    def test_dropin_later_value_wins(self):
        result = s.parse_cat_output(CAT_TWO_FILES)
        # override.conf sets Domain=bar, should win
        assert result["X-Labels"]["Domain"] == "bar"
        # key only in base file survives
        assert result["X-Labels"]["Project"] == "myapp"
        # key only in drop-in is present
        assert result["X-Labels"]["Extra"] == "yes"

    def test_no_custom_section_returns_empty_dict(self):
        result = s.parse_cat_output(CAT_NO_CUSTOM_SECTION)
        assert "X-Labels" not in result

    def test_empty_output_returns_empty_dict(self):
        assert s.parse_cat_output(CAT_EMPTY) == {}

    def test_comments_are_ignored(self):
        result = s.parse_cat_output(CAT_SINGLE_FILE)
        for section in result.values():
            for key in section:
                assert not key.startswith("#")

    def test_value_with_equals_sign(self):
        raw = """\
# /etc/systemd/system/eq.service
[X-Labels]
Cmd=/bin/sh -c 'echo a=b'
"""
        result = s.parse_cat_output(raw)
        assert result["X-Labels"]["Cmd"] == "/bin/sh -c 'echo a=b'"

    def test_whitespace_stripped_from_key_and_value(self):
        raw = """\
# /etc/systemd/system/ws.service
[X-Labels]
  Key  =  value with spaces
"""
        result = s.parse_cat_output(raw)
        assert "Key" in result["X-Labels"]
        assert result["X-Labels"]["Key"] == "value with spaces"


# ---------------------------------------------------------------------------
# parse_label_filters
# ---------------------------------------------------------------------------

class TestParseLabelFilters:
    def test_key_only(self):
        assert s.parse_label_filters(["Project"]) == [("Project", None)]

    def test_key_value(self):
        assert s.parse_label_filters(["Project=myapp"]) == [("Project", "myapp")]

    def test_multiple_mixed(self):
        result = s.parse_label_filters(["Project=myapp", "Domain", "Env=prod"])
        assert result == [("Project", "myapp"), ("Domain", None), ("Env", "prod")]

    def test_empty_list(self):
        assert s.parse_label_filters([]) == []

    def test_strips_whitespace(self):
        assert s.parse_label_filters([" Project "]) == [("Project", None)]
        assert s.parse_label_filters([" Key = val "]) == [("Key", "val")]

    def test_value_containing_equals(self):
        # Only the first '=' is the separator
        result = s.parse_label_filters(["Cmd=/bin/sh -c 'a=b'"])
        assert result == [("Cmd", "/bin/sh -c 'a=b'")]


# ---------------------------------------------------------------------------
# section_matches
# ---------------------------------------------------------------------------

SECTION = {"Project": "myapp", "Domain": "foo", "Env": "prod"}


class TestSectionMatches:
    def test_key_only_present(self):
        assert s.section_matches(SECTION, [("Project", None)]) is True

    def test_key_only_missing(self):
        assert s.section_matches(SECTION, [("Missing", None)]) is False

    def test_key_value_match(self):
        assert s.section_matches(SECTION, [("Project", "myapp")]) is True

    def test_key_value_wrong_value(self):
        assert s.section_matches(SECTION, [("Project", "other")]) is False

    def test_multiple_filters_all_match(self):
        filters = [("Project", "myapp"), ("Domain", "foo"), ("Env", None)]
        assert s.section_matches(SECTION, filters) is True

    def test_multiple_filters_one_missing(self):
        filters = [("Project", "myapp"), ("Ghost", None)]
        assert s.section_matches(SECTION, filters) is False

    def test_multiple_filters_one_wrong_value(self):
        filters = [("Project", "myapp"), ("Domain", "bar")]
        assert s.section_matches(SECTION, filters) is False

    def test_empty_filters_always_true(self):
        assert s.section_matches(SECTION, []) is True

    def test_empty_section_with_filters(self):
        assert s.section_matches({}, [("Project", None)]) is False

    def test_empty_section_empty_filters(self):
        assert s.section_matches({}, []) is True


# ---------------------------------------------------------------------------
# section_excluded
# ---------------------------------------------------------------------------

class TestSectionExcluded:
    def test_key_present_excludes(self):
        # --exclude Domain  →  Domain exists in section, so unit is excluded
        assert s.section_excluded(SECTION, [("Domain", None)]) is True

    def test_key_absent_does_not_exclude(self):
        # --exclude Ghost  →  Ghost not in section, unit passes through
        assert s.section_excluded(SECTION, [("Ghost", None)]) is False

    def test_key_value_match_excludes(self):
        # --exclude Domain=foo  →  exact match, unit is excluded
        assert s.section_excluded(SECTION, [("Domain", "foo")]) is True

    def test_key_value_wrong_value_does_not_exclude(self):
        # --exclude Domain=bar  →  Domain exists but value differs, unit passes
        assert s.section_excluded(SECTION, [("Domain", "bar")]) is False

    def test_key_value_missing_key_does_not_exclude(self):
        # --exclude Ghost=foo  →  key absent entirely, unit passes
        assert s.section_excluded(SECTION, [("Ghost", "foo")]) is False

    def test_multiple_filters_any_match_excludes(self):
        # First filter misses, second hits → still excluded
        filters = [("Ghost", None), ("Domain", None)]
        assert s.section_excluded(SECTION, filters) is True

    def test_multiple_filters_none_match_passes(self):
        filters = [("Ghost", None), ("Another", "val")]
        assert s.section_excluded(SECTION, filters) is False

    def test_empty_filters_never_excludes(self):
        assert s.section_excluded(SECTION, []) is False

    def test_empty_section_key_only_does_not_exclude(self):
        # Key can't be present in an empty section
        assert s.section_excluded({}, [("Project", None)]) is False

    def test_empty_section_key_value_does_not_exclude(self):
        assert s.section_excluded({}, [("Project", "myapp")]) is False


# ---------------------------------------------------------------------------
# format_json_entry
# ---------------------------------------------------------------------------

class TestFormatJsonEntry:
    def test_enabled_active_unit(self):
        entry = s.format_json_entry("foo.service", "enabled", True, {"Project": "myapp"})
        assert entry["name"] == "foo.service"
        assert entry["enabled"] is True
        assert entry["is-active"] is True
        assert entry["labels"] == {"Project": "myapp"}

    def test_disabled_inactive_unit(self):
        entry = s.format_json_entry("bar.service", "disabled", False, {"Project": "myapp"})
        assert entry["enabled"] is False
        assert entry["is-active"] is False

    def test_static_unit_counts_as_enabled(self):
        entry = s.format_json_entry("baz.service", "static", False, {})
        assert entry["enabled"] is True

    def test_masked_unit_counts_as_disabled(self):
        entry = s.format_json_entry("baz.service", "masked", False, {})
        assert entry["enabled"] is False

    def test_labels_are_full_section_copy(self):
        section = {"Project": "myapp", "Domain": "foo", "Env": "prod"}
        entry = s.format_json_entry("foo.service", "enabled", True, section)
        assert entry["labels"] == section
        # Mutations to the returned dict must not affect the original
        entry["labels"]["Extra"] = "x"
        assert "Extra" not in section

    def test_empty_labels(self):
        entry = s.format_json_entry("foo.service", "enabled", True, {})
        assert entry["labels"] == {}

    def test_required_keys_present(self):
        entry = s.format_json_entry("foo.service", "enabled", True, {})
        assert set(entry.keys()) == {"name", "enabled", "is-active", "labels"}


# ---------------------------------------------------------------------------
# format_verbose
# ---------------------------------------------------------------------------

class TestFormatVerbose:
    def test_shows_queried_keys_only(self):
        section = {"Project": "myapp", "Domain": "foo", "Extra": "ignored"}
        filters = [("Project", "myapp"), ("Domain", None)]
        line = s.format_verbose("foo.service", section, filters)
        assert "foo.service" in line
        assert "Project=myapp" in line
        assert "Domain=foo" in line
        assert "Extra" not in line

    def test_no_filters_shows_all_keys(self):
        section = {"Project": "myapp", "Domain": "foo"}
        line = s.format_verbose("foo.service", section, [])
        assert "Project=myapp" in line
        assert "Domain=foo" in line

    def test_unit_name_always_present(self):
        line = s.format_verbose("bar.service", {}, [])
        assert "bar.service" in line

    def test_tab_separator_between_name_and_labels(self):
        section = {"Project": "myapp"}
        filters = [("Project", None)]
        line = s.format_verbose("foo.service", section, filters)
        assert "\t" in line
        name, labels = line.split("\t", 1)
        assert name == "foo.service"
        assert "Project=myapp" in labels

    def test_queried_key_absent_in_section_skipped(self):
        section = {"Domain": "foo"}
        filters = [("Project", None), ("Domain", None)]
        line = s.format_verbose("foo.service", section, filters)
        assert "Domain=foo" in line
        assert "Project" not in line
