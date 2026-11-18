import json

import pytest
from typer.testing import CliRunner

from tests.conftest import AS_OF
from uw_agent.agent import ProfilePipeline
from uw_agent.agent.confidence import compute_confidence
from uw_agent.cli import app
from uw_agent.resolution import EntityResolver
from uw_agent.schema.profile import (
    ConfidenceLevel,
    Conflict,
    ConflictType,
    ProfileStatus,
    RecommendedAction,
    Severity,
)

A = RecommendedAction


@pytest.fixture(scope="module")
def pipeline(repo):
    return ProfilePipeline(repo, EntityResolver.from_repository(repo, alias_file=None))


def build(pipeline, name, **kw):
    return pipeline.build(name, as_of=AS_OF, **kw)


def rule_ids(profile):
    return {r.rule_id for r in profile.assessment.triggered_rules}


def test_confirmed_critical_sanction_declines_and_short_circuits(pipeline):
    p = build(pipeline, "PDG")
    assert p.assessment.recommended_action is A.DECLINE
    assert "R1" in rule_ids(p)
    assert p.trace.short_circuit and p.public_information.status == "skipped"
    # Internal summaries are still computed after a short-circuit.
    assert p.relationship is not None and p.claims_performance is not None
    types = {c.type for c in p.conflicts}
    assert ConflictType.WATCHLIST_LINKED_BY_NAME_ONLY in types


def test_possible_flag_never_declines(pipeline):
    p = build(pipeline, "Grupo Quimera S.A.")
    assert p.status is ProfileStatus.AMBIGUOUS
    assert p.assessment.recommended_action is A.REFER_TO_COMPLIANCE  # R2b precedes R3
    assert {"R2b", "R3"} <= rule_ids(p)
    nova2 = next(c for c in p.candidates_summary if c.client_id == "N2")
    assert nova2.active_flags == ["sancion_regulatoria/crítico"]


def test_state_hint_avoids_possible_flag(pipeline):
    p = build(pipeline, "Grupo Quimera S.A.", state="Jalisco")
    assert p.company_identity.client_id == "N1"
    assert p.risk_flags == []


def test_resolved_flag_with_contradicting_note_refers(pipeline):
    p = build(pipeline, "Constructora Morelos S.A. de C.V.")
    conflict = next(c for c in p.conflicts if c.type is ConflictType.WATCHLIST_NOTE_VS_STATUS)
    assert conflict.severity is Severity.HIGH
    assert "R5e" in rule_ids(p)


def test_credible_high_loss_ratio_and_disputes_refer(pipeline):
    p = build(pipeline, "Transportes Delta S.A. de C.V.")
    assert {"R5c", "R5d"} <= rule_ids(p)
    assert p.assessment.recommended_action is A.REFER_TO_SENIOR_UNDERWRITER


def test_thin_loss_ratio_triggers_no_rule(pipeline):
    p = build(pipeline, "Industrias Omega S.C.")
    assert not {"R5c", "R6c"} & rule_ids(p)


def test_homonym_resolution_reports_ambiguity_and_possible_flag(pipeline):
    p = build(pipeline, "Tecnologías Arcoíris S.A. de C.V.")
    assert p.status is ProfileStatus.COMPLETE and p.company_identity.client_id == "BIG"
    assert ConflictType.ENTITY_AMBIGUITY in {c.type for c in p.conflicts}
    assert ConflictType.INDUSTRY_NAME_MISMATCH in {c.type for c in p.conflicts}
    assert "R6b" in rule_ids(p)


def test_related_entities_in_profile(pipeline):
    p = build(pipeline, "HSBC México S.A.")
    assert [r.name for r in p.related_entities] == ["BITAL SA"]


def test_not_found(pipeline):
    p = build(pipeline, "Panificadora Sol Naciente S.A.")
    assert p.status is ProfileStatus.NOT_FOUND
    assert p.assessment.recommended_action is A.INSUFFICIENT_INFORMATION


def test_invalid_input(pipeline):
    p = build(pipeline, "S.A. de C.V.")
    assert p.status is ProfileStatus.INVALID_INPUT
    assert p.assessment.recommended_action is A.INSUFFICIENT_INFORMATION


def test_trace_records_every_step(pipeline):
    p = build(pipeline, "Transportes Delta S.A. de C.V.")
    assert [s.step for s in p.trace.steps] == [
        "entity_resolution",
        "watchlist_screening",
        "client_history",
        "related_entities",
        "web_research",
        "assessment",
    ]


def test_confidence_cap_for_weak_entity():
    c = compute_confidence(entity=0.5, internal=1.0, conflicts=[])
    assert c.overall == 0.4 and c.capped and c.level is ConfidenceLevel.LOW


def test_entity_ambiguity_is_not_penalised_twice():
    amb = Conflict(
        id="C1",
        type=ConflictType.ENTITY_AMBIGUITY,
        severity=Severity.MEDIUM,
        description="",
        sources=[],
    )
    other = Conflict(
        id="C2",
        type=ConflictType.INDUSTRY_NAME_MISMATCH,
        severity=Severity.MEDIUM,
        description="",
        sources=[],
    )
    assert compute_confidence(1.0, 1.0, [amb]).conflict_penalty == 0
    assert compute_confidence(1.0, 1.0, [amb, other]).conflict_penalty == 0.07


@pytest.mark.parametrize(
    ("args", "code"),
    [
        (["profile", "PDG", "--as-of", "2025-06-30"], 0),
        (["profile", "", "--as-of", "2025-06-30"], 2),
        (["profile", "PDG", "--as-of", "30/06/2025"], 2),
    ],
)
def test_cli_exit_codes(monkeypatch, repo, args, code):
    monkeypatch.setattr("uw_agent.cli._repo", lambda settings: repo)
    result = CliRunner().invoke(app, args)
    assert result.exit_code == code
    if code == 0:
        assert json.loads(result.stdout)["status"] == "COMPLETE"


def test_cli_missing_data_exits_1(monkeypatch, tmp_path):
    monkeypatch.setenv("UW_DATA_DIR", str(tmp_path))
    assert CliRunner().invoke(app, ["profile", "PDG"]).exit_code == 1
