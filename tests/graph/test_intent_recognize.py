import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.graph.nodes import intent_recognize, State


@pytest.mark.asyncio
async def test_intent_recognize_batch_doc_gen_extracts_task_file_path():
    """intent_recognize extracts task_file_path and stores it in config."""
    state: State = {
        "messages": [MagicMock(content="根据 ubill-access-api/task.md 生成文档")],
        "intent": "",
        "task_file_paths": [],
        "generated_doc_paths": [],
    }
    config = {"configurable": {}}

    mock_response = MagicMock()
    mock_response.content = '{"intent": "batch_doc_gen", "task_file_path": "ubill-access-api/task.md"}'

    with patch("src.graph.nodes.get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_get_llm.return_value = mock_llm

        result = await intent_recognize(state, config)

    assert result["intent"] == "batch_doc_gen"
    assert config["configurable"]["task_file_path"] == "ubill-access-api/task.md"