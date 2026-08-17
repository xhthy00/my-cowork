from app.guardrails.policy import check_tool_allowed


class TestCheckToolAllowed:
    def test_exact_match_allowed(self) -> None:
        assert check_tool_allowed({"allowed_tools": ["builtin.fs.write"]}, "builtin.fs.write") is True

    def test_exact_match_denied(self) -> None:
        assert check_tool_allowed({"allowed_tools": ["builtin.fs.write"]}, "lark.send") is False

    def test_wildcard_suffix_allows_matching_tool(self) -> None:
        assert check_tool_allowed({"allowed_tools": ["mcp.github.*"]}, "mcp.github.get_pr") is True

    def test_wildcard_suffix_denies_non_matching_namespace(self) -> None:
        assert check_tool_allowed({"allowed_tools": ["mcp.github.*"]}, "mcp.slack.send") is False

    def test_broad_wildcard_allows_nested_tools(self) -> None:
        assert check_tool_allowed({"allowed_tools": ["mcp.*"]}, "mcp.github.get_pr") is True

    def test_empty_whitelist_denies_everything(self) -> None:
        assert check_tool_allowed({"allowed_tools": []}, "builtin.fs.write") is False

    def test_missing_whitelist_denies_everything(self) -> None:
        assert check_tool_allowed({}, "builtin.fs.write") is False

    def test_wildcard_at_start_matches_suffix(self) -> None:
        assert check_tool_allowed({"allowed_tools": ["*.write"]}, "builtin.fs.write") is True
        assert check_tool_allowed({"allowed_tools": ["*.write"]}, "builtin.fs.read") is False

    def test_multiple_patterns_one_matches(self) -> None:
        assert check_tool_allowed(
            {"allowed_tools": ["builtin.fs.*", "lark.send"]},
            "builtin.fs.read",
        ) is True
        assert check_tool_allowed(
            {"allowed_tools": ["builtin.fs.*", "lark.send"]},
            "lark.send",
        ) is True
        assert check_tool_allowed(
            {"allowed_tools": ["builtin.fs.*", "lark.send"]},
            "mcp.github.get_pr",
        ) is False
