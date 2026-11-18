import json

import pytest

from tests.conftest import AS_OF
from uw_agent.agent import ProfilePipeline
from uw_agent.batch import BatchInputError, BatchItem, read_inputs, run_batch
from uw_agent.resolution import EntityResolver


@pytest.fixture
def pipeline(repo):
    return ProfilePipeline(repo, EntityResolver.from_repository(repo, alias_file=None))


def lines(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_read_txt_skips_comments_and_blanks(tmp_path):
    f = tmp_path / "in.txt"
    f.write_text("PDG\n# comment\n\n  Grupo Quimera S.A.  \n", encoding="utf-8")
    assert read_inputs(f) == [BatchItem("PDG"), BatchItem("Grupo Quimera S.A.")]


def test_read_csv_with_state(tmp_path):
    f = tmp_path / "in.csv"
    f.write_text("name,state\nGrupo Quimera S.A.,Jalisco\nPDG,\n", encoding="utf-8")
    assert read_inputs(f) == [BatchItem("Grupo Quimera S.A.", "Jalisco"), BatchItem("PDG")]


@pytest.mark.parametrize("content", ["company,state\nPDG,\n", "\n# only comments\n"])
def test_bad_inputs(tmp_path, content):
    f = tmp_path / ("in.csv" if "," in content else "in.txt")
    f.write_text(content, encoding="utf-8")
    with pytest.raises(BatchInputError):
        read_inputs(f)


def test_failure_isolation_dedup_and_order(tmp_path, pipeline, monkeypatch):
    original = pipeline.build

    def flaky(name, as_of, state=None):
        if name == "Boom":
            raise RuntimeError("synthetic failure")
        return original(name, as_of=as_of, state=state)

    calls = []

    def recording(name, as_of, state=None):
        calls.append(name)
        return flaky(name, as_of, state)

    monkeypatch.setattr(pipeline, "build", recording)
    out = tmp_path / "out.jsonl"
    items = [
        BatchItem("PDG"),
        BatchItem("Boom"),
        BatchItem("pdg"),
        BatchItem("Grupo Quimera S.A."),
    ]
    summary = run_batch(pipeline, items, out, AS_OF, workers=3)

    rows = lines(out)
    assert [r["query"]["input_name"] for r in rows] == ["PDG", "Boom", "pdg", "Grupo Quimera S.A."]
    assert rows[1]["status"] == "ERROR" and "synthetic failure" in rows[1]["assessment"]["summary"]
    assert sorted(calls) == ["Boom", "Grupo Quimera S.A.", "PDG"]  # pdg deduplicated
    assert summary["errors"] == ["Boom"] and summary["this_run"]["deduplicated"] == 1
    assert (tmp_path / "out.summary.json").exists()


def test_resume_skips_done_inputs(tmp_path, pipeline):
    out = tmp_path / "out.jsonl"
    run_batch(pipeline, [BatchItem("PDG")], out, AS_OF)
    summary = run_batch(pipeline, [BatchItem("PDG"), BatchItem("Grupo Quimera S.A.")], out, AS_OF)
    assert summary["this_run"]["skipped_already_done"] == 1
    assert summary["profiles"] == 2 and len(lines(out)) == 2


def test_overwrite(tmp_path, pipeline):
    out = tmp_path / "out.jsonl"
    run_batch(pipeline, [BatchItem("PDG")], out, AS_OF)
    run_batch(pipeline, [BatchItem("PDG")], out, AS_OF, overwrite=True)
    assert len(lines(out)) == 1
