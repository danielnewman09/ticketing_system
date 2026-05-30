"""Integration test: verify design_verify SYSTEM_PROMPT renders correctly."""

from backend.ticketing_agent.design_verify.combined_prompt import SYSTEM_PROMPT


def test_system_prompt_renders():
    """SYSTEM_PROMPT renders with all placeholder sections empty."""
    rendered = SYSTEM_PROMPT.format(
        specializations_section="",
        namespace_section="",
        as_built_section="",
        existing_classes_section="",
        intercomponent_section="",
    )
    # Should contain the key structural elements
    assert "FORMAT-CONTRACT" in rendered
    assert "digraph design_verify_workflow" in rendered
    assert "[Good]" in rendered
    assert "[Bad]" in rendered
    # Should NOT contain removed elements
    assert "twelve tools available" not in rendered
    assert "### Discovery tools" not in rendered
    assert "### Design & verification tools" not in rendered
    assert "DISCOVERY PHASE" not in rendered
    assert "✓" not in rendered
    assert "✗" not in rendered
    # Should contain FORMAT-CONTRACT content
    assert "qualified-names" in rendered
    assert "verification-key-format" in rendered
    # Should contain instruction content (no longer has a ## Instructions header)
    assert "### For the design" in rendered


def test_system_prompt_renders_with_sections():
    """SYSTEM_PROMPT renders with non-empty placeholder sections."""
    rendered = SYSTEM_PROMPT.format(
        specializations_section="## Specializations\n- C++",
        namespace_section="The required namespace is: `calculation_engine`",
        as_built_section="",
        existing_classes_section="",
        intercomponent_section="",
    )
    assert "Specializations" in rendered
    assert "calculation_engine" in rendered
    # Verify the new guidance sections are present
    assert "Enum values in conditions" in rendered
    assert "Do NOT restructure your design to match verification stub references" in rendered