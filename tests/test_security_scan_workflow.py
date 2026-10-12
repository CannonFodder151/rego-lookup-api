"""Regression test for the rego-lookup-api security gate (AUT-4776).

GitHub silently drops a workflow file that declares a duplicate mapping key,
so the whole file is parsed as invalid and NO check-run is ever created. That
left the resolved-tree pip-audit gate (AUT-1189), the digest pin guard and
the base-image trivy scan (AUT-1735) unexecuted on every push to main since
2026-09-22. These assertions fail against the broken file and pass after the
fix.

Run: python3 tests/test_security_scan_workflow.py
"""

import re
import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github/workflows/security-scan.yml"
DOCKERFILE = REPO / "Dockerfile"
REQUIREMENTS = REPO / "requirements.txt"


class StrictLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of silently
    keeping the last one, which is exactly the failure GitHub applies."""


def _no_duplicate_keys(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise AssertionError(f"duplicate mapping key {key!r} at line {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


def load_workflow():
    return yaml.load(WORKFLOW.read_text(), Loader=StrictLoader)


class SecurityScanWorkflowTest(unittest.TestCase):
    # Load lazily (memoised) rather than in setUpClass: a duplicate-key file
    # must fail each affected test individually, not abort the whole class
    # in setUpClass and hide which defects were caught.
    _text = None
    _wf = None
    _dockerfile = None

    @property
    def text(self):
        if self._text is None:
            self._text = WORKFLOW.read_text()
        return self._text

    @property
    def wf(self):
        if self._wf is None:
            self._wf = load_workflow()
        return self._wf

    @property
    def dockerfile(self):
        if self._dockerfile is None:
            self._dockerfile = DOCKERFILE.read_text()
        return self._dockerfile

    def test_workflow_parses_without_duplicate_keys(self):
        # The whole point of AUT-4776: GitHub drops the file outright.
        self.assertIsInstance(self.wf, dict)

    def test_single_top_level_jobs_key(self):
        # 'jobs' parses as a mapping key, never the YAML bool True.
        self.assertEqual(len(re.findall(r"(?m)^jobs:", self.text)), 1)
        self.assertIn("jobs", self.wf)

    def test_all_three_security_jobs_present(self):
        # Subset check, not equality: the gate may gain non-security jobs
        # (workflow-lint was added by AUT-4776 follow-up) but these three must
        # never disappear.
        for job in ("audit", "image-scan", "pip-audit-pr"):
            with self.subTest(job=job):
                self.assertIn(job, self.wf["jobs"])

    def test_workflow_lint_runs_in_docker_with_no_bytecode(self):
        # AUT-6315: workflow-lint runs inside the pinned base image because the
        # self-hosted runner lacks ensurepip. AUT-6319: PYTHONDONTWRITEBYTECODE=1
        # prevents root-owned __pycache__ in the mounted workspace, which breaks
        # subsequent job checkouts.
        lint = self.wf["jobs"]["workflow-lint"]
        script = "\n".join(s.get("run", "") for s in lint["steps"])
        self.assertIn("docker run", script, "workflow-lint must run inside the pinned image")
        self.assertIn("$PYTHON_BASE_IMAGE", script)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", script, "must set PYTHONDONTWRITEBYTECODE=1 to avoid root-owned __pycache__")
        self.assertIn("__pycache__", script, "must clean up any __pycache__ created by the docker run")

    def test_pre_checkout_pycache_cleanup_in_all_self_hosted_jobs(self):
        # AUT-6319: root-owned __pycache__ from prior docker runs block
        # actions/checkout@v4 git clean. Every self-hosted job must clean
        # __pycache__ before checkout.
        for job_name, job in self.wf["jobs"].items():
            runs_on = job.get("runs-on", [])
            if isinstance(runs_on, str):
                runs_on = [runs_on]
            if "self-hosted" not in runs_on:
                continue
            with self.subTest(job=job_name):
                steps = job["steps"]
                checkout_idx = next(
                    (i for i, s in enumerate(steps) if s.get("uses", "").startswith("actions/checkout")),
                    None,
                )
                self.assertIsNotNone(checkout_idx, f"{job_name} must have a checkout step")
                pre_checkout = steps[:checkout_idx]
                found = any(
                    "__pycache__" in s.get("run", "") and "docker run" in s.get("run", "")
                    for s in pre_checkout
                )
                self.assertTrue(found, f"{job_name} must clean __pycache__ via docker run before checkout")

    def test_jobs_are_not_shadowed(self):
        # A duplicate `jobs:` silently discards the first block; make sure the
        # PR-time pip-audit gate is actually the one that survives.
        self.assertIn("pip-audit-pr", self.wf["jobs"])

    def _pin_guard_pattern(self):
        m = re.search(r"grep -nE '([^']+)' Dockerfile", self.text)
        self.assertIsNotNone(m, "pin guard grep pattern not found")
        return m.group(1)

    @staticmethod
    def _flagged(dockerfile_text, pattern):
        """Replicate the guard: FROM lines matching the pattern, minus any
        carrying @sha256. Whatever survives is what the guard would flag."""
        lines = [l for l in dockerfile_text.splitlines() if re.search(pattern, l, re.M)]
        return [l for l in lines if "@sha256" not in l]

    def test_pin_guard_regex_matches_real_from_line(self):
        # Old pattern 'FROM python:[0-9]' matched nothing because the Dockerfile
        # uses 'FROM --platform=$TARGETPLATFORM python:...', so the guard passed
        # vacuously and enforced nothing.
        self.assertIsNotNone(
            re.search(self._pin_guard_pattern(), self.dockerfile, re.M),
            "pin guard pattern must match the real FROM line",
        )

    def test_pin_guard_passes_on_current_pinned_dockerfile(self):
        self.assertEqual(self._flagged(self.dockerfile, self._pin_guard_pattern()), [])

    def test_pin_guard_still_rejects_a_floating_tag(self):
        # Guard must be effective, not merely non-vacuous: swapping the pinned
        # line for a floating tag must be flagged.
        pattern = self._pin_guard_pattern()
        floating = self.dockerfile.replace(
            re.search(r"^FROM .*python:[\d.]+-slim@sha256:[a-f0-9]+", self.dockerfile, re.M).group(0),
            "FROM --platform=$TARGETPLATFORM python:3.13-slim",
        )
        self.assertNotEqual(floating, self.dockerfile, "could not build floating-tag fixture")
        self.assertTrue(self._flagged(floating, pattern), "floating base image must be flagged")

    def test_scanned_image_matches_dockerfile_digest(self):
        # Drift meant trivy audited an image the service no longer ships.
        pat = r"python:[\d.]+-slim@sha256:([a-f0-9]{64})"
        scanned = set(re.findall(pat, self.text))
        shipped = set(re.findall(pat, self.dockerfile))
        self.assertTrue(shipped, "Dockerfile has no pinned python base digest")
        self.assertEqual(scanned, shipped, "PYTHON_BASE_IMAGE drifted from Dockerfile")

    def test_pip_audit_does_not_depend_on_host_venv(self):
        # The runner's system python has no ensurepip, so `python3 -m venv` on
        # the host always failed and the AUT-1189 gate produced a false
        # negative. The audit must run inside the pinned base image.
        job = self.wf["jobs"]["pip-audit-pr"]
        script = "\n".join(s.get("run", "") for s in job["steps"])
        self.assertIn("python3 -m venv", script, "expected a venv inside the container")
        self.assertIn("docker run", script, "audit must run in the pinned image")
        self.assertIn("$PYTHON_BASE_IMAGE", script)
        # The old host-venv form built its venv via mktemp outside any
        # container; that is the variant that broke on the runner.
        self.assertNotIn("mktemp", script, "host mktemp venv must be gone")
        self.assertRegex(script, r"python3 -m venv /tmp/venv")
        # pip-audit must be installed into that venv, not on the host: a bare
        # `pip-audit` call against a fresh venv exits 127 (command not found),
        # which reads as a CVE failure but is really a missing-tool failure.
        self.assertRegex(script, r"pip install --quiet pip-audit")
        lines = script.splitlines()
        install_idx = next(i for i, l in enumerate(lines) if "pip install --quiet pip-audit" in l)
        audit_idx = next(i for i, l in enumerate(lines) if l.strip() == "pip-audit")
        self.assertLess(install_idx, audit_idx, "install pip-audit before invoking it")

    def test_pip_audit_runs_on_self_hosted(self):
        # AUT-5962 (2026-10-07): moved back to self-hosted because GitHub-hosted
        # ubuntu-latest runners were not scheduling jobs (0 steps, immediate failure).
        # The OOM that motivated the original move to ubuntu-latest was transient.
        runs_on = self.wf["jobs"]["pip-audit-pr"]["runs-on"]
        self.assertEqual(runs_on, ["self-hosted", "linux", "x64"])


class CveFloorPinTest(unittest.TestCase):
    """AUT-4780: known-CVE packages must carry a version floor in
    requirements.txt.

    A bare transitive dep resolves to whatever satisfies its parent's range,
    so a widened upstream constraint silently reintroduces a patched CVE. The
    AUT-1189 pins exist for this reason; urllib3 was the one that got missed
    because requests declares only urllib3<3,>=1.26.
    """

    # package -> (minimum safe version, CVEs fixed at or above it)
    FLOORS = {
        "idna": ("3.15", ("PYSEC-2026-215", "GHSA-65pc-fj4g-8rjx")),
        "pygments": ("2.20", ("PYSEC-2023-117", "PYSEC-2026-2987")),
        "urllib3": ("2.8.0", ("CVE-2026-97687", "CVE-2026-97689")),
    }

    def _pins(self):
        """Map package name -> version specifier for every non-comment line."""
        pins = {}
        for line in REQUIREMENTS.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            for op in ("==", ">=", "<=", "~=", ">", "<"):
                if op in line:
                    name, _, version = line.partition(op)
                    pins[name.strip()] = (op, version.strip())
                    break
            else:
                self.fail(f"unparsable requirement line: {line!r}")
        return pins

    def test_every_known_cve_package_has_a_floor_pin(self):
        pins = self._pins()
        missing = [pkg for pkg in self.FLOORS if pkg not in pins]
        self.assertFalse(
            missing,
            f"no floor pin in requirements.txt for {missing}; a widened upstream "
            f"constraint would resolve them to a vulnerable version again",
        )

    def test_floor_pins_are_lower_bounds(self):
        # A floor must constrain from below. An `==` pin does too, but a bare
        # `urllib3` with no specifier would not, and neither would a stale
        # upper-bound-only entry.
        pins = self._pins()
        for pkg, (minimum, _) in self.FLOORS.items():
            with self.subTest(package=pkg):
                if pkg not in pins:
                    # Reported as a clean failure by
                    # test_every_known_cve_package_has_a_floor_pin; don't raise
                    # a KeyError here on top of it.
                    self.fail(f"{pkg} has no floor pin at all")
                op, version = pins[pkg]
                self.assertIn(op, (">=", "=="), f"{pkg} must be pinned low, got {op}{version}")
                self.assertGreaterEqual(
                    _v(version), _v(minimum), f"{pkg} floor {version} is below the fixed version {minimum}"
                )

    def test_urllib3_floor_is_not_regressed(self):
        # The specific AUT-4780 regression: dropping the urllib3 line entirely
        # must fail. requests==2.34.2 allows urllib3<3,>=1.26, so without an
        # explicit floor a build can land on 1.26.0-2.7.x.
        pins = self._pins()
        self.assertIn("urllib3", pins, "AUT-4780: urllib3 floor pin was removed")
        _, version = pins["urllib3"]
        self.assertGreaterEqual(
            _v(version), _v("2.8.0"), "urllib3 must stay at or above 2.8.0 (CVE-2026-97687/97689)"
        )


def _v(spec):
    """Compare only the numeric release, so '3.15' and '3.15.1' both parse."""
    parts = []
    for chunk in spec.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


if __name__ == "__main__":
    result = unittest.main(argv=[sys.argv[0], "-v"], exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
