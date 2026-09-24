from agent_runtime.agents.coding.skill_registry import SkillRegistry


def test_custom_skill_overrides_bundled_copy_and_stays_deleted(tmp_path):
    builtins = tmp_path / "builtins"
    custom = tmp_path / "custom"
    builtins.mkdir()
    custom.mkdir()
    (builtins / "custom_example.md").write_text("# Skill: Example\n\nPurpose: bundled\n")
    file = custom / "custom_example.md"
    file.write_text("# Skill: Example\n\nPurpose: edited\n")

    assert SkillRegistry(builtins, custom).load().get("custom_example").purpose == "edited"

    file.unlink()
    (custom / "custom_example.deleted").write_text("")
    assert not SkillRegistry(builtins, custom).load().has("custom_example")
