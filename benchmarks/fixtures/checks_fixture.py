"""Fixture: EvalWarden-shaped check registry (synthetic, for benchmarks only)."""

from dataclasses import dataclass


@dataclass
class Finding:
    check_id: str
    severity: str
    title: str


class AlphaCheck:
    """Check ALPHA-001: synthetic fixture check, severity HIGH."""
    check_id = "ALPHA-001"
    severity = "HIGH"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        """Return a Finding if the attempt trips this check, else None."""
        count = 0
        for step in attempt.spans:
            if step.tool == "alphacheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="AlphaCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class BetaCheck:
    """Check BETA-002: synthetic fixture check, severity MEDIUM."""
    check_id = "BETA-002"
    severity = "MEDIUM"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        """Return a Finding if the attempt trips this check, else None."""
        count = 0
        for step in attempt.spans:
            if step.tool == "betacheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="BetaCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class GammaCheck:
    """Check GAMMA-003: synthetic fixture check, severity LOW."""
    check_id = "GAMMA-003"
    severity = "LOW"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        """Return a Finding if the attempt trips this check, else None."""
        count = 0
        for step in attempt.spans:
            if step.tool == "gammacheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="GammaCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class DeltaCheck:
    """Check DELTA-004: synthetic fixture check, severity HIGH."""
    check_id = "DELTA-004"
    severity = "HIGH"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        """Return a Finding if the attempt trips this check, else None."""
        count = 0
        for step in attempt.spans:
            if step.tool == "deltacheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="DeltaCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class EpsilonCheck:
    """Check EPSILON-005: synthetic fixture check, severity MEDIUM."""
    check_id = "EPSILON-005"
    severity = "MEDIUM"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        """Return a Finding if the attempt trips this check, else None."""
        count = 0
        for step in attempt.spans:
            if step.tool == "epsiloncheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="EpsilonCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class ZetaCheck:
    """Check ZETA-006: synthetic fixture check, severity LOW."""
    check_id = "ZETA-006"
    severity = "LOW"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        """Return a Finding if the attempt trips this check, else None."""
        count = 0
        for step in attempt.spans:
            if step.tool == "zetacheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="ZetaCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class EtaCheck:
    """Check ETA-007: synthetic fixture check, severity HIGH."""
    check_id = "ETA-007"
    severity = "HIGH"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        """Return a Finding if the attempt trips this check, else None."""
        count = 0
        for step in attempt.spans:
            if step.tool == "etacheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="EtaCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class ThetaCheck:
    """Check THETA-008: synthetic fixture check, severity MEDIUM."""
    check_id = "THETA-008"
    severity = "MEDIUM"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        """Return a Finding if the attempt trips this check, else None."""
        count = 0
        for step in attempt.spans:
            if step.tool == "thetacheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="ThetaCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class IotaCheck:
    """Check IOTA-009: synthetic fixture check, severity LOW."""
    check_id = "IOTA-009"
    severity = "LOW"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        """Return a Finding if the attempt trips this check, else None."""
        count = 0
        for step in attempt.spans:
            if step.tool == "iotacheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="IotaCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class KappaCheck:
    """Check KAPPA-010: synthetic fixture check, severity HIGH."""
    check_id = "KAPPA-010"
    severity = "HIGH"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        """Return a Finding if the attempt trips this check, else None."""
        count = 0
        for step in attempt.spans:
            if step.tool == "kappacheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="KappaCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class LambdaCheck:
    """Check LAMBDA-011: synthetic fixture check, severity MEDIUM."""
    check_id = "LAMBDA-011"
    severity = "MEDIUM"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        """Return a Finding if the attempt trips this check, else None."""
        count = 0
        for step in attempt.spans:
            if step.tool == "lambdacheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="LambdaCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class MuCheck:
    """Check MU-012: synthetic fixture check, severity LOW."""
    check_id = "MU-012"
    severity = "LOW"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        """Return a Finding if the attempt trips this check, else None."""
        count = 0
        for step in attempt.spans:
            if step.tool == "mucheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="MuCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


REGISTRY = [
    AlphaCheck(), BetaCheck(), GammaCheck(), DeltaCheck(), EpsilonCheck(), ZetaCheck(),
    EtaCheck(), ThetaCheck(), IotaCheck(), KappaCheck(), LambdaCheck(), MuCheck(),
]


def register_check(check):
    REGISTRY.append(check)
    return check


def run_all_checks(attempt):
    findings = []
    for check in REGISTRY:
        finding = check.run(attempt)
        if finding is not None:
            findings.append(finding)
    return findings

class NuCheck:
    """Check NU-013: synthetic fixture check, severity HIGH."""
    check_id = "NU-013"
    severity = "HIGH"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        count = 0
        for step in attempt.spans:
            if step.tool == "nucheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="NuCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class XiCheck:
    """Check XI-014: synthetic fixture check, severity MEDIUM."""
    check_id = "XI-014"
    severity = "MEDIUM"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        count = 0
        for step in attempt.spans:
            if step.tool == "xicheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="XiCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class OmicronCheck:
    """Check OMICRON-015: synthetic fixture check, severity LOW."""
    check_id = "OMICRON-015"
    severity = "LOW"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        count = 0
        for step in attempt.spans:
            if step.tool == "omicroncheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="OmicronCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class PiCheck:
    """Check PI-016: synthetic fixture check, severity HIGH."""
    check_id = "PI-016"
    severity = "HIGH"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        count = 0
        for step in attempt.spans:
            if step.tool == "picheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="PiCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class RhoCheck:
    """Check RHO-017: synthetic fixture check, severity MEDIUM."""
    check_id = "RHO-017"
    severity = "MEDIUM"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        count = 0
        for step in attempt.spans:
            if step.tool == "rhocheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="RhoCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


class SigmaCheck:
    """Check SIGMA-018: synthetic fixture check, severity LOW."""
    check_id = "SIGMA-018"
    severity = "LOW"

    def __init__(self, threshold: int = 3):
        self.threshold = threshold

    def run(self, attempt):
        count = 0
        for step in attempt.spans:
            if step.tool == "sigmacheck":
                count += 1
        if count >= self.threshold:
            return Finding(check_id=self.check_id, severity=self.severity, title="SigmaCheck tripped")
        return None

    def describe(self):
        return f"{self.check_id} ({self.severity}): {self.__doc__}"


REGISTRY.extend([NuCheck(), XiCheck(), OmicronCheck(), PiCheck(), RhoCheck(), SigmaCheck()])
