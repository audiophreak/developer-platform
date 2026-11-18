import pytest

from devkit.errors import UsageError
from devkit.profiles import DEFAULT_PROFILE, PROFILES, ProfileError, VersionRange, get_profile


def test_web_core_is_the_only_available_profile() -> None:
    assert DEFAULT_PROFILE == "web-core"
    assert [p.id for p in PROFILES.values() if p.available] == ["web-core"]
    assert get_profile("web-core").title == "Web Core"


@pytest.mark.parametrize("profile", ["full-stack", "native-ios"])
def test_reserved_profiles_are_rejected_with_a_clear_message(profile: str) -> None:
    with pytest.raises(ProfileError, match="reserved for a later milestone"):
        get_profile(profile)


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ProfileError, match="Unknown profile"):
        get_profile("nope")


def test_profile_errors_are_usage_errors() -> None:
    assert issubclass(ProfileError, UsageError) and ProfileError.exit_code == 2


def test_web_core_declares_its_template_contract() -> None:
    template = get_profile("web-core").template
    assert template.url.startswith("https://") and template.url.endswith(".git")
    assert template.node_major == 26
    assert [o.name for o in template.options] == ["cache_components", "zod", "forms", "rest_api", "database", "auth"]
    assert {o.name: o.default for o in template.options} == {
        "cache_components": True, "zod": False, "forms": False, "rest_api": False, "database": "none", "auth": False,
    }  # fmt: skip
    assert str(template.versions) == ">=0.1.0,<0.7.0"  # 0.1.x to 0.6.x stay supported
    assert {o.name: o.since for o in template.options} == {
        "cache_components": (0, 1, 0), "zod": (0, 2, 0), "forms": (0, 3, 0), "rest_api": (0, 4, 0), "database": (0, 5, 0), "auth": (0, 6, 0),
    }  # fmt: skip
    database = next(o for o in template.options if o.name == "database")
    assert database.kind == "str" and database.choices == ("none", "postgres", "supabase") and database.sticky and "zod" in database.help


def test_only_available_profiles_carry_a_template() -> None:
    for profile in PROFILES.values():
        assert (profile.template is not None) == profile.available


def test_version_range_is_half_open() -> None:
    supported = VersionRange((0, 1, 0), (0, 2, 0))
    assert supported.contains((0, 1, 0)) and supported.contains((0, 1, 99))
    assert not supported.contains((0, 0, 9)) and not supported.contains((0, 2, 0))


def test_no_option_needs_a_release_newer_than_the_newest_supported_one() -> None:
    template = get_profile("web-core").template
    newest_possible = (template.versions.maximum_exclusive[0], template.versions.maximum_exclusive[1] - 1, 99)
    for option in template.options:
        assert option.since <= newest_possible, option.name
