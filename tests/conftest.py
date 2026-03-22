"""
Jinja2 mock environment for testing CCA blueprint conditions without Home Assistant.

HA-specific functions (states, is_state, etc.) are replaced with Python callables
that read from a simple dict of entity_id → state string.
"""
import jinja2
import pytest


def make_jinja_env(entity_states: dict | None = None) -> jinja2.Environment:
    """
    Return a Jinja2 Environment with mocked HA global functions.

    entity_states: dict mapping entity_id → state string, e.g.
        {"binary_sensor.window": "on", "binary_sensor.resident": "off"}
    """
    entity_states = entity_states or {}

    def states(entity_id):
        return entity_states.get(entity_id, "unknown")

    def is_state(entity_id, state):
        return entity_states.get(entity_id) == state

    env = jinja2.Environment(undefined=jinja2.Undefined)
    env.globals["states"] = states
    env.globals["is_state"] = is_state
    return env


def eval_condition(env: jinja2.Environment, condition: str, variables: dict) -> bool:
    """
    Evaluate a single Jinja2 condition string (without {{ }}) given variables.
    The condition must evaluate to a truthy/falsy value.
    """
    # Strip leading/trailing {{ }} if present (blueprint style)
    cond = condition.strip()
    if cond.startswith("{{") and cond.endswith("}}"):
        cond = cond[2:-2].strip()
    template = env.from_string("{{ " + cond + " }}")
    result = template.render(**variables)
    # Jinja2 renders booleans as "True"/"False"
    if result == "True":
        return True
    if result == "False":
        return False
    # Treat non-empty strings as truthy (like Jinja2 does)
    return bool(result.strip())


def eval_conditions(env: jinja2.Environment, conditions: list[str], variables: dict) -> bool:
    """Return True only if ALL conditions evaluate to True (AND logic)."""
    return all(eval_condition(env, c, variables) for c in conditions)


def first_matching_branch(env: jinja2.Environment, branches: list[dict], variables: dict) -> str | None:
    """
    Simulate a choose: block. Each branch is {"name": str, "conditions": [str]}.
    Returns the name of the first branch whose conditions all pass, or None.
    """
    for branch in branches:
        if eval_conditions(env, branch["conditions"], variables):
            return branch["name"]
    return None
