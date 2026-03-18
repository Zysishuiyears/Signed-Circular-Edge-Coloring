from __future__ import annotations

from pathlib import Path

from signedcoloring.io import dump_instance, load_instance, write_json


def test_instance_roundtrip_preserves_edge_ids(tmp_path: Path) -> None:
    source = (
        Path(__file__).resolve().parents[1] / "data" / "instances" / "single_positive_edge.json"
    )
    instance = load_instance(source)

    target = tmp_path / "instance.json"
    write_json(target, dump_instance(instance))
    reloaded = load_instance(target)

    assert reloaded.name == instance.name
    assert reloaded.vertices == instance.vertices
    assert [edge.id for edge in reloaded.edges] == [edge.id for edge in instance.edges]
