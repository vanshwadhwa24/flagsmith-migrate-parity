"""Example legacy flag system (the "before" state). Written for this project.

on  = enabled AND every rule matches AND (no rollout OR bucket(flag, user) < rollout_percent)
"""
import hashlib


def bucket(flag, user_id):
    return int(hashlib.md5(f"{flag}:{user_id}".encode()).hexdigest(), 16) % 100


def rule_matches(rule, attrs):
    got, want, op = attrs.get(rule["attribute"]), rule["value"], rule.get("operator", "eq")
    if op == "eq":
        return str(got) == str(want)
    if op == "in":
        return str(got) in [x.strip() for x in str(want).split(",")]
    raise ValueError(f"unknown operator {op}")


def evaluate(flag, user_id, attrs):
    if not flag.get("enabled", True):
        return False
    if not all(rule_matches(r, attrs) for r in flag.get("rules", [])):
        return False
    if "rollout_percent" in flag:
        return bucket(flag["name"], user_id) < flag["rollout_percent"]
    return True
