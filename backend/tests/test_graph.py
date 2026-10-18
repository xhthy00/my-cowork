"""Legacy worker names and product intent classification."""

from dataclasses import dataclass
from pathlib import Path
import time

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool as langchain_tool

from app.graphs.routing import (
    infer_default_worker,
    needs_forced_delegation,
    parse_workers,
)
from app.observability.trace import TraceBus
from tests.conftest import FakeChatModel, make_ai


class TestParseWorkers:
    def test_parallel_protocol(self):
        assert parse_workers("PARALLEL:file_worker,doc_worker") == [
            "developer_agent",
            "document_agent",
        ]

    def test_finish(self):
        assert parse_workers("FINISH") == []

    def test_natural_language_routing(self):
        assert parse_workers("The doc_worker needs to handle this request.") == [
            "document_agent"
        ]


class TestInferDefaultWorker:
    def test_ppt_followup_beats_travel_keywords(self):
        q = "帮我将上述的旅游攻略生成图文并茂的 PPT 版攻略"
        assert infer_default_worker(q) == "document_agent"

    def test_research_still_web(self):
        assert infer_default_worker("帮我搜索宜昌旅游攻略") == "browser_agent"

    def test_short_ppt_forces_delegation(self):
        assert needs_forced_delegation("生成PPT") is True
        assert infer_default_worker("生成PPT") == "document_agent"

    def test_unspecified_report_goes_to_document_agent(self):
        assert infer_default_worker("做成一份报告") == "document_agent"
        assert infer_default_worker("写一份报告") == "document_agent"

    def test_web_game_goes_to_developer_agent(self):
        assert infer_default_worker("帮我开发一个坦克大战的web网页游戏") == "developer_agent"
