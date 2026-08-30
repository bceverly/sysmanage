# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.

"""Server-side engine registry and per-engine readiness (Phase 20.1).

Two properties carry the weight here.

**Package names are measured, never guessed.** Guessing cost us twice on
ansible-core, and the puppet cell proves the point again: the package that
provides `/usr/bin/puppet` is `puppet-agent`, and a package literally named
`puppet` does not exist. A test pins that so nobody "tidies" it.

**An absent engine is not a deficiency.** A host without Puppet simply does not
use Puppet, so the ordering leads with what the host HAS and the statuses
distinguish "cannot install here" from "cannot detect here" -- conflating them
would tell a Windows operator that Puppet is unavailable on Windows, which is
false.
"""

from backend.services import config_mgmt_engines as engines
from backend.services import config_mgmt_plan_builder as planner
from backend.services import config_mgmt_prereq as prereq


def host(platform, release=""):
    return {"platform": platform, "platform_release": release}


def pkg(name, version):
    return {"package_name": name, "package_version": version}


class TestIdentitiesMatchTheAgent:
    def test_the_identity_set_is_the_contract(self):
        # These strings are written into config_profile_run.executor and into
        # profile documents. The agent has its own copy; if the two drift, a
        # profile naming an engine the agent knows becomes unroutable.
        assert set(engines.ALL_ENGINES) == {
            "ansible-core",
            "puppet",
            "salt",
            "chef",
            "dsc",
        }

    def test_identities_are_never_binaries(self):
        assert engines.CHEF == "chef"
        assert engines.PUPPET == "puppet"
        assert engines.SALT == "salt"


class TestMeasuredPackages:
    def test_puppet_installs_from_puppet_agent_not_puppet(self):
        # Measured on Ubuntu 2026-08-27: `apt-cache policy puppet` reports no
        # candidate at all, while puppet-agent 8.10.0-6 provides
        # /usr/bin/puppet (confirmed with dpkg -S). Using the binary name as
        # the package name installs nothing.
        assert engines.package_for("puppet", "apt") == "puppet-agent"

    def test_chef_is_packaged_under_its_own_name_on_apt(self):
        assert engines.package_for("chef", "apt") == "chef"

    def test_salt_is_recorded_as_absent_from_apt_rather_than_guessed(self):
        # Positively established: Salt is not in Ubuntu's repositories, so an
        # apt install cannot work. Recorded explicitly so the knowledge is not
        # lost and nobody "fixes" it with a plausible-looking name.
        assert engines.package_for("salt", "apt") is None

    def test_an_unmeasured_cell_is_none_not_a_guess(self):
        assert engines.package_for("puppet", "zypper") is None
        assert engines.package_for("chef", "apk") is None


class TestPlatformApplicability:
    def test_windows_is_not_locked_to_dsc(self):
        # Puppet, Salt and Chef all ship Windows agents.
        applicable = engines.applicable("windows")
        for engine in ("puppet", "salt", "chef", "ansible-core"):
            assert engine in applicable

    def test_dsc_is_offered_only_on_windows(self):
        assert "dsc" in engines.applicable("windows")
        assert "dsc" not in engines.applicable("linux")


class TestPerEngineEvaluation:
    def test_installed_engines_are_listed_first(self):
        # The card leads with what the host has, not with what it lacks.
        results = prereq.evaluate_all(
            host("Linux", "Ubuntu 24.04"),
            [pkg("puppet-agent", "8.10.0")],
        )
        assert results[0]["engine"] == "puppet"
        assert results[0]["status"] == prereq.STATUS_SATISFIED

    def test_several_engines_can_be_ready_at_once(self):
        results = prereq.evaluate_all(
            host("Linux", "Ubuntu 24.04"),
            [pkg("ansible-core", "2.20.1"), pkg("puppet-agent", "8.10.0")],
        )
        ready = {r["engine"] for r in results if r["status"] == prereq.STATUS_SATISFIED}
        assert ready == {"ansible-core", "puppet"}

    def test_an_absent_but_installable_engine_offers_an_install(self):
        # ansible-core, not chef: chef is a licensed adapter and deliberately
        # never offers an install button (see TestLicensing).
        results = {
            r["engine"]: r
            for r in prereq.evaluate_all(host("Linux", "Ubuntu 24.04"), [])
        }
        assert results["ansible-core"]["status"] == prereq.STATUS_MISSING
        assert results["ansible-core"]["can_install"] is True

    def test_an_engine_the_distro_does_not_carry_offers_nothing(self):
        results = {
            r["engine"]: r
            for r in prereq.evaluate_all(host("Linux", "Ubuntu 24.04"), [])
        }
        assert results["salt"]["status"] == prereq.STATUS_UNSUPPORTED
        assert results["salt"]["can_install"] is False

    def test_windows_reports_a_detection_limit_not_a_platform_limit(self):
        # Saying "not available on this platform" for Puppet on Windows would
        # be false -- we simply cannot read the inventory for it there.
        results = {r["engine"]: r for r in prereq.evaluate_all(host("Windows"), [])}
        assert results["puppet"]["detail"] == "detection_unavailable_on_windows"
        assert results["dsc"]["status"] == prereq.STATUS_NOT_REQUIRED

    def test_dsc_is_bundled_not_satisfied(self):
        results = {r["engine"]: r for r in prereq.evaluate_all(host("Windows"), [])}
        assert results["dsc"]["detail"] == "bundled_with_agent"
        assert results["dsc"]["can_install"] is False

    def test_dsc_is_not_listed_off_windows(self):
        engines_seen = {
            r["engine"] for r in prereq.evaluate_all(host("Linux", "Ubuntu 24.04"), [])
        }
        assert "dsc" not in engines_seen

    def test_only_ansible_has_a_version_floor(self):
        # A floor we have not measured would strand working hosts, so the
        # other engines deliberately have none.
        old_ansible = prereq.evaluate_engine(
            "ansible-core", host("Linux", "Ubuntu 24.04"), [pkg("ansible-core", "2.14")]
        )
        assert old_ansible["status"] == prereq.STATUS_TOO_OLD

        old_puppet = prereq.evaluate_engine(
            "puppet", host("Linux", "Ubuntu 24.04"), [pkg("puppet-agent", "5.0.0")]
        )
        assert old_puppet["status"] == prereq.STATUS_SATISFIED

    def test_an_engine_that_cannot_run_here_is_unsupported(self):
        result = prereq.evaluate_engine("dsc", host("Linux", "Ubuntu 24.04"), [])
        assert result["status"] == prereq.STATUS_UNSUPPORTED
        assert result["detail"] == "not_applicable_on_platform"


class TestBackwardCompatibility:
    def test_the_single_engine_api_still_answers_for_the_default(self):
        # The apply endpoint and the existing card still call evaluate(); the
        # refactor must not change what they see.
        result = prereq.evaluate(
            host("Linux", "Ubuntu 24.04"), [pkg("ansible-core", "2.20.1")]
        )
        assert result["status"] == prereq.STATUS_SATISFIED
        assert result["executor"] == "ansible-core"

    def test_windows_still_reports_not_required_through_the_old_api(self):
        assert prereq.evaluate(host("Windows"))["status"] == prereq.STATUS_NOT_REQUIRED


class TestLicensing:
    """Which engines an OSS build may drive (decided 2026-08-27).

    The line is NOT "config management is Enterprise". ansible-core and DSC
    stay free because single-host apply is the direct analogue of
    execute_script, which is free -- gating it would be unenforceable (wrap the
    playbook in a shell script) as well as mean-spirited. Puppet, Salt and Chef
    are the migration bridge, whose value is proportional to an existing estate
    nobody accumulates at three hosts.
    """

    def test_ansible_and_dsc_are_free(self):
        assert engines.requires_license("ansible-core") is False
        assert engines.requires_license("dsc") is False

    def test_the_migration_adapters_are_licensed(self):
        for engine in ("puppet", "salt", "chef"):
            assert engines.requires_license(engine) is True, engine

    def test_every_engine_is_classified(self):
        # A new engine added without a licensing decision would silently
        # default to free.
        assert engines.OSS_ENGINES | engines.LICENSED_ENGINES == set(
            engines.ALL_ENGINES
        )
        assert not (engines.OSS_ENGINES & engines.LICENSED_ENGINES)

    def test_an_unknown_engine_is_not_treated_as_licensed(self):
        # It should be rejected as unknown, not gated -- a 400, not a 403.
        assert engines.requires_license("terraform") is False

    def test_licensed_engines_never_offer_an_install_button(self):
        # Offering one would 403 on press. The row is still RETURNED so a
        # Puppet shop evaluating SysManage can see Puppet is supported rather
        # than concluding it is missing.
        results = {
            r["engine"]: r
            for r in prereq.evaluate_all(host("Linux", "Ubuntu 24.04"), [])
        }
        assert results["chef"]["status"] == prereq.STATUS_MISSING
        assert results["chef"]["can_install"] is False
        assert results["chef"]["requires_license"] is True

    def test_free_engines_still_offer_their_install(self):
        results = {
            r["engine"]: r
            for r in prereq.evaluate_all(host("Linux", "Ubuntu 24.04"), [])
        }
        assert results["ansible-core"]["can_install"] is True
        assert results["ansible-core"]["requires_license"] is False


class TestLicensedInstall:
    """A customer who paid for the adapters must be able to install them.

    The first cut suppressed the install button for every licensed engine
    unconditionally, reasoning that an unlicensed press would 403. That was
    right for an unlicensed install and wrong for a paying one: it told a
    customer who had just bought Puppet support to go install Puppet by hand,
    which is the friction the prerequisite card exists to remove.
    """

    def test_unlicensed_offers_no_install_for_a_paid_adapter(self):
        rows = {
            r["engine"]: r
            for r in prereq.evaluate_all(
                host("Linux", "Ubuntu 24.04"), [], engine_licence_available=False
            )
        }
        assert rows["puppet"]["can_install"] is False
        assert rows["chef"]["can_install"] is False

    def test_licensed_offers_the_install(self):
        rows = {
            r["engine"]: r
            for r in prereq.evaluate_all(
                host("Linux", "Ubuntu 24.04"), [], engine_licence_available=True
            )
        }
        assert rows["puppet"]["can_install"] is True
        assert rows["chef"]["can_install"] is True

    def test_a_licence_cannot_conjure_a_package_that_does_not_exist(self):
        # Salt is genuinely absent from Ubuntu's repositories. Paying for the
        # adapter does not put it there, so the row stays unsupported.
        rows = {
            r["engine"]: r
            for r in prereq.evaluate_all(
                host("Linux", "Ubuntu 24.04"), [], engine_licence_available=True
            )
        }
        assert rows["salt"]["status"] == prereq.STATUS_UNSUPPORTED
        assert rows["salt"]["can_install"] is False

    def test_the_free_engine_is_unaffected_by_licence_state(self):
        for licensed in (False, True):
            rows = {
                r["engine"]: r
                for r in prereq.evaluate_all(
                    host("Linux", "Ubuntu 24.04"), [], engine_licence_available=licensed
                )
            }
            assert rows["ansible-core"]["can_install"] is True


class TestPerEngineInstallPlans:
    def test_puppet_installs_the_agent_package_not_the_binary_name(self):
        # `apt-cache policy puppet` has no candidate; /usr/bin/puppet ships in
        # puppet-agent. Measured 2026-08-27.
        plan = planner.build_engine_install_plan(
            "puppet", host("Linux", "Ubuntu 24.04")
        )
        assert plan["packages"] == [{"manager": "apt", "name": "puppet-agent"}]

    def test_chef_installs_under_its_own_name(self):
        plan = planner.build_engine_install_plan("chef", host("Linux", "Ubuntu 24.04"))
        assert plan["packages"] == [{"manager": "apt", "name": "chef"}]

    def test_salt_on_apt_bootstraps_the_vendor_repository(self):
        # Ubuntu still does not ship Salt -- that premise has not changed, and
        # `package_for(salt, apt)` is still None. What changed 2026-08-30 is
        # that "not in the distro" no longer means "no plan": apt gets the
        # vendor repository added first, so the answer is an install rather
        # than a shrug. dnf/zypper are still unmeasured and still get None.
        plan = planner.build_engine_install_plan("salt", host("Linux", "Ubuntu 24.04"))
        assert plan is not None
        assert engines.package_for("salt", "apt") is None
        assert ["apt-get", "install", "-y", "salt-common"] in [
            c["argv"] for c in plan["commands"]
        ]

    def test_salt_elsewhere_still_has_no_plan(self):
        for hostinfo in (host("Linux", "Fedora 41"), host("Linux", "openSUSE")):
            assert planner.build_engine_install_plan("salt", hostinfo) is None

    def test_ansible_still_goes_through_its_measured_per_platform_path(self):
        # FreeBSD's py3* glob is an ansible-specific quirk that must survive.
        plan = planner.build_engine_install_plan("ansible-core", host("FreeBSD"))
        assert "py3*-ansible-core" in plan["commands"][0]["argv"]

    def test_an_omitted_engine_falls_back_to_the_platform_default(self):
        assert planner.build_engine_install_plan(
            "", host("Linux", "Ubuntu 24.04")
        ) == planner.build_install_plan(host("Linux", "Ubuntu 24.04"))

    def test_no_windows_plans_are_guessed(self):
        # MSI/choco installs for these are unmeasured; refusing beats guessing.
        for engine in ("puppet", "chef", "salt"):
            assert planner.build_engine_install_plan(engine, host("Windows")) is None
