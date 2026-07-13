"""
Structural tests for the apply_transition architecture (CCA 2026.07.03).

Every leaf branch of the action tree computes exactly two things —
`update_values` (the state transition) and optionally `drive_plan` (the
actuation plan) — and then calls the shared *apply_transition anchor, which
performs: optional delay -> optional drive -> unconditional helper persist.

These tests turn the architectural invariants into enforceable structure:

  1. Invariant 2 / Bug Pattern AK: a step that sets update_values or
     drive_plan must be followed by a persisting step (the resolved
     apply_transition anchor) in its own sequence or in the shared tail of
     an ancestor sequence (classification-style handlers like Manual/Reset
     set update_values inside a choose and persist once after it).
  2. No branch may bypass apply_transition: the raw *helper_update alias is
     only allowed inside the apply_transition anchor itself and in the
     v5 -> v6 migration persist; raw *drive_with_actions / *tilt_move_action
     aliases are only allowed inside anchor definitions.
"""
import pathlib

import yaml


BLUEPRINT_PATH = (
    pathlib.Path(__file__).parent.parent
    / "blueprints"
    / "automation"
    / "cover_control_automation.yaml"
)


def _load_blueprint_yaml() -> dict:
    class _Loader(yaml.SafeLoader):
        pass

    _Loader.add_constructor(
        "!input",
        lambda loader, node: loader.construct_scalar(node),
    )
    with open(BLUEPRINT_PATH, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)  # noqa: S506


def _persists_helper(step) -> bool:
    """True when the step (with YAML aliases resolved) writes the helper."""
    return "input_text.set_value" in str(step)


def _collect_violations(actions: list) -> list[str]:
    """
    Walk every sequence in the action tree. For each step that defines
    update_values or drive_plan, require a helper-persisting step later in
    the same sequence or later in an ancestor sequence (shared-tail pattern).
    """
    violations: list[str] = []

    def has_persist_in_tail(ancestors: list[tuple[list, int]]) -> bool:
        for seq, idx in ancestors:
            for later in seq[idx + 1 :]:
                if _persists_helper(later):
                    return True
        return False

    def walk_step(step, ancestors):
        if not isinstance(step, dict):
            return
        variables = step.get("variables")
        if isinstance(variables, dict) and (
            "update_values" in variables or "drive_plan" in variables
        ):
            if not has_persist_in_tail(ancestors):
                keys = [k for k in ("update_values", "drive_plan") if k in variables]
                violations.append(
                    f"step defining {keys} is not followed by a helper persist "
                    f"(apply_transition) in its sequence or an ancestor tail"
                )
        # Recurse into every nested sequence-bearing structure.
        for key in ("sequence", "then", "else", "default"):
            nested = step.get(key)
            if isinstance(nested, list):
                walk_sequence(nested, ancestors)
        for branch in step.get("choose") or []:
            if isinstance(branch, dict) and isinstance(branch.get("sequence"), list):
                walk_sequence(branch["sequence"], ancestors)

    def walk_sequence(seq: list, ancestors):
        for idx, step in enumerate(seq):
            walk_step(step, ancestors + [(seq, idx)])

    walk_sequence(actions, [])
    return violations


class TestEveryTransitionIsPersisted:
    """Invariant 2 / Bug Pattern AK, enforced structurally."""

    def test_every_update_values_step_reaches_a_persist(self):
        blueprint = _load_blueprint_yaml()
        actions = blueprint.get("actions") or blueprint.get("action")
        assert actions, "action tree missing"
        # Skip the anchor-definition variables step (actions[0]): its bodies
        # are definitions, not executions.
        violations = _collect_violations(actions[1:])
        assert violations == [], "\n".join(violations)


class TestNoBypassOfApplyTransition:
    """All persists and drives must flow through the shared anchors."""

    def test_raw_helper_update_alias_only_in_anchor_and_migration(self):
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        # 1x inside the apply_transition anchor, 1x v5->v6 migration persist.
        assert text.count("- *helper_update") == 2, (
            "leaf branches must persist via *apply_transition, not raw "
            "*helper_update"
        )

    def test_raw_drive_aliases_only_inside_anchors(self):
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        # *drive_with_actions: 1x inside apply_transition.
        assert text.count("- *drive_with_actions") == 1, (
            "leaf branches must drive via *apply_transition, not raw "
            "*drive_with_actions"
        )
        # *tilt_move_action: 2x inside drive_with_actions (default order and
        # tilt-before-position order), 1x inside apply_transition (move: tilt).
        assert text.count("- *tilt_move_action") == 3, (
            "leaf branches must tilt via *apply_transition (move: tilt), not "
            "raw *tilt_move_action"
        )

    def test_apply_transition_is_used_pervasively(self):
        text = BLUEPRINT_PATH.read_text(encoding="utf-8")
        assert text.count("- *apply_transition") >= 40, (
            "expected the leaf branches of the action tree to call "
            "*apply_transition"
        )


class TestApplyTransitionAnchorShape:
    """The anchor itself: delay/drive only with a plan, persist always."""

    def test_anchor_persists_unconditionally(self):
        blueprint = _load_blueprint_yaml()
        anchors = blueprint["actions"][0]["variables"]
        anchor = anchors.get("apply_transition")
        assert anchor is not None, "apply_transition anchor missing"
        seq = anchor["sequence"]
        # Last step must be the unconditional helper persist.
        assert _persists_helper(seq[-1]), (
            "apply_transition must end with the helper persist"
        )
        # The drive must be gated on drive_plan.run.
        drive_step = next(s for s in seq if isinstance(s, dict) and "if" in s)
        assert "drive_plan" in str(drive_step["if"]) and "run" in str(drive_step["if"])

    def test_anchor_guards_are_prerender_safe(self):
        # Invariant 14: every drive_plan reference inside the anchor body must
        # be default-guarded because the anchor is pre-rendered on every run.
        blueprint = _load_blueprint_yaml()
        anchor = blueprint["actions"][0]["variables"]["apply_transition"]
        flat = str(anchor)
        assert "drive_plan | default({})" in flat, (
            "anchor body must guard drive_plan with | default({}) "
            "(Invariant 14: anchor bodies are pre-rendered)"
        )
        # No unguarded direct attribute access on drive_plan.
        import re

        unguarded = re.findall(r"(?<!\()drive_plan\.\w+", flat)
        assert unguarded == [], f"unguarded drive_plan references: {unguarded}"


class TestForcePauseIsPartOfEveryDriveGate:
    """The force pause suspends every movement. The move actions themselves are
    guarded (cover_move_action / tilt_move_action check is_paused), but Invariant 7
    ties the man: reset - and drive_with_actions ties the user's before/after
    actions - to the DRIVE DECISION, not to the move action. A drive gate that
    ignores the pause therefore cleared the manual override and fired the user's
    notifications while nothing could move. Every gate must know the pause."""

    def _walk_drive_gates(self):
        """Yield (context, will_drive_template, drive_plan) for every leaf branch,
        tracking whether an enclosing if already checks is_paused."""
        blueprint = _load_blueprint_yaml()
        found = []

        def walk(node, pause_guarded):
            if isinstance(node, dict):
                guard = pause_guarded or (
                    "is_paused" in str(node.get("if", "")) or
                    "is_paused" in str(node.get("conditions", ""))
                )
                variables = node.get("variables")
                if isinstance(variables, dict) and (
                    "will_drive" in variables or "drive_plan" in variables
                ):
                    found.append((variables.get("will_drive"),
                                  variables.get("drive_plan"), guard))
                for key, value in node.items():
                    if key in ("then", "else", "sequence", "default"):
                        walk(value, guard)
                    elif key not in ("if", "conditions"):
                        walk(value, pause_guarded)
            elif isinstance(node, list):
                for item in node:
                    walk(item, pause_guarded)

        walk(blueprint["actions"], False)
        return found

    def test_every_drive_gate_respects_the_force_pause(self):
        gates = self._walk_drive_gates()
        assert len(gates) >= 25, "expected to find the leaf-branch drive gates"
        violations = []
        for will_drive, drive_plan, guarded in gates:
            gate = str(will_drive) if will_drive is not None else ""
            plan = str(drive_plan) if drive_plan is not None else ""
            if will_drive is not None:
                # A will_drive definition must carry the pause itself (state_gates do).
                if "is_paused" not in gate and "state_gates" not in gate:
                    violations.append(gate[:120])
                continue
            # A drive_plan without its own will_drive step: either it references a
            # will_drive defined in an earlier step of the same branch (checked above,
            # e.g. the recovery gate), carries the pause itself, sits under an
            # is_paused-checking if (run: true), or does not drive at all.
            if ("will_drive" in plan or "is_paused" in plan or guarded
                    or "run" not in plan):
                continue
            violations.append(plan[:120])
        assert violations == [], violations

    def test_state_gates_block_while_paused(self):
        import jinja2

        blueprint = _load_blueprint_yaml()
        gates = None
        for step in blueprint["actions"]:
            if isinstance(step, dict) and "state_gates" in step.get("variables", {}):
                gates = step["variables"]["state_gates"]
        assert gates is not None
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)
        permissive = dict(
            force_allows_ventilate=True, force_allows_open=True,
            force_allows_shade=True, force_allows_close=True,
            effective_state="none_of_them",
            in_open_position=False, in_ventilate_position=False,
            in_shading_position=False, in_close_position=False,
        )
        for state, tpl in gates.items():
            assert env.from_string(tpl).render(is_paused=False, **permissive).strip() == "True", state
            assert env.from_string(tpl).render(is_paused=True, **permissive).strip() == "False", state

    def test_the_users_drive_actions_stay_quiet_while_paused(self):
        """drive_with_actions opens with a condition guard, same mechanic as
        cover_move_action: a false condition stops only this block, the helper
        persist after it still runs (Invariant 2)."""
        blueprint = _load_blueprint_yaml()
        anchor = blueprint["actions"][0]["variables"]["drive_with_actions"]
        first = anchor["sequence"][0]
        assert first.get("condition") == "template"
        assert "is_paused" in str(first.get("value_template", ""))
