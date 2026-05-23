"""Unit tests for _is_valid_verification_qname (no Neo4j needed)."""


class TestValidVerificationQname:
    """Unit tests for _is_valid_verification_qname (no Neo4j needed)."""

    def test_valid_qualified_name(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("calculation_engine::CalculatorEngine::add")
        assert is_valid is True
        assert corrected is None

    def test_valid_two_part_qname(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("user_interface::CalculatorWindow")
        assert is_valid is True
        assert corrected is None

    def test_dot_separator_auto_corrected(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("user_interface::CalculatorWindow.equalsButton")
        assert is_valid is True
        assert corrected == "user_interface::CalculatorWindow::equalsButton"

    def test_nested_dot_separator_auto_corrected(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("CalculatorEngine.last_result.is_success")
        assert is_valid is True
        assert corrected == "CalculatorEngine::last_result::is_success"

    def test_reject_test_prefix(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("test_validate_input_syntax")
        assert is_valid is False

    def test_reject_result_of_prefix(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("result_of_first_call")
        assert is_valid is False

    def test_reject_bare_lowercase(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("value")
        assert is_valid is False

    def test_reject_empty_string(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("")
        assert is_valid is False

    def test_reject_none(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname(None)
        assert is_valid is False

    def test_reject_decimal_number(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("5.0")
        assert is_valid is False

    def test_reject_verify_prefix(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("verify_display_area_exists")
        assert is_valid is False

    def test_reject_check_prefix(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("check_input_valid")
        assert is_valid is False

    def test_valid_enum_value_qname(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("calculation_engine::Operation::ADD")
        assert is_valid is True
        assert corrected is None

    def test_reject_purely_numeric_component(self):
        from backend.db.neo4j.repositories.verification import _is_valid_verification_qname
        is_valid, corrected = _is_valid_verification_qname("3")
        assert is_valid is False