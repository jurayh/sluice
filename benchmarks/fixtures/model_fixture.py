"""Fixture: EvalWarden-shaped trajectory model (synthetic, for benchmarks only)."""

from dataclasses import dataclass, field

@dataclass
class TrajectoryStep:
    step_id: str
    tool: str
    args: dict
    output: str
    spans: list = field(default_factory=list)

    def summary(self):
        return f"{self.__class__.__name__} with {len(self.spans)} spans"

@dataclass
class Attempt:
    task_id: str
    status: str
    tool_calls: int
    spans: list = field(default_factory=list)

    def summary(self):
        return f"{self.__class__.__name__} with {len(self.spans)} spans"

@dataclass
class TaskSample:
    id: str
    prompt: str
    spans: list = field(default_factory=list)

    def summary(self):
        return f"{self.__class__.__name__} with {len(self.spans)} spans"

@dataclass
class IntegrityModel:
    eval_id: str
    adapter_name: str
    adapter_version: str
    spans: list = field(default_factory=list)

    def summary(self):
        return f"{self.__class__.__name__} with {len(self.spans)} spans"


def build_attempt(task_id, steps):
    attempt = Attempt(task_id=task_id, status="incomplete", tool_calls=len(steps))
    attempt.spans = steps
    return attempt


def count_tools(attempt):
    counts = {}
    for step in attempt.spans:
        counts[step.tool] = counts.get(step.tool, 0) + 1
    return counts


def helper_00(value):
    """Synthetic helper 00: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_01(value):
    """Synthetic helper 01: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_02(value):
    """Synthetic helper 02: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_03(value):
    """Synthetic helper 03: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_04(value):
    """Synthetic helper 04: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_05(value):
    """Synthetic helper 05: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_06(value):
    """Synthetic helper 06: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_07(value):
    """Synthetic helper 07: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_08(value):
    """Synthetic helper 08: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_09(value):
    """Synthetic helper 09: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_10(value):
    """Synthetic helper 10: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_11(value):
    """Synthetic helper 11: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_12(value):
    """Synthetic helper 12: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_13(value):
    """Synthetic helper 13: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_14(value):
    """Synthetic helper 14: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_15(value):
    """Synthetic helper 15: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_16(value):
    """Synthetic helper 16: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_17(value):
    """Synthetic helper 17: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_18(value):
    """Synthetic helper 18: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_19(value):
    """Synthetic helper 19: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_20(value):
    """Synthetic helper 20: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_21(value):
    """Synthetic helper 21: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_22(value):
    """Synthetic helper 22: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_23(value):
    """Synthetic helper 23: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_24(value):
    """Synthetic helper 24: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_25(value):
    """Synthetic helper 25: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_26(value):
    """Synthetic helper 26: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_27(value):
    """Synthetic helper 27: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value

def helper_28(value):
    """Synthetic helper 28: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_29(value):
    """Synthetic helper 29: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_30(value):
    """Synthetic helper 30: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_31(value):
    """Synthetic helper 31: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_32(value):
    """Synthetic helper 32: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_33(value):
    """Synthetic helper 33: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_34(value):
    """Synthetic helper 34: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_35(value):
    """Synthetic helper 35: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_36(value):
    """Synthetic helper 36: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_37(value):
    """Synthetic helper 37: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_38(value):
    """Synthetic helper 38: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_39(value):
    """Synthetic helper 39: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_40(value):
    """Synthetic helper 40: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_41(value):
    """Synthetic helper 41: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_42(value):
    """Synthetic helper 42: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_43(value):
    """Synthetic helper 43: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_44(value):
    """Synthetic helper 44: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_45(value):
    """Synthetic helper 45: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_46(value):
    """Synthetic helper 46: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_47(value):
    """Synthetic helper 47: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_48(value):
    """Synthetic helper 48: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_49(value):
    """Synthetic helper 49: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_50(value):
    """Synthetic helper 50: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_51(value):
    """Synthetic helper 51: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_52(value):
    """Synthetic helper 52: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_53(value):
    """Synthetic helper 53: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_54(value):
    """Synthetic helper 54: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_55(value):
    """Synthetic helper 55: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_56(value):
    """Synthetic helper 56: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_57(value):
    """Synthetic helper 57: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_58(value):
    """Synthetic helper 58: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value


def helper_59(value):
    """Synthetic helper 59: returns value unchanged, for fixture length."""
    if value is None:
        return None
    return value
