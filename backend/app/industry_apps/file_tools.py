"""Narrow file operations for plugin tasks, without shell or arbitrary path access."""
from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.task_support.app_context import app_task_scope


class ReadFile(BaseModel):
    file_id: str


class WriteReport(BaseModel):
    content: str = Field(min_length=1, max_length=200000)


def make_app_file_tools():
    async def read_file(file_id: str):
        scope = app_task_scope.get()
        if not scope or 'app_read_file' not in scope.tools or file_id not in scope.files:
            raise PermissionError('文件未授权给此任务')
        path = Path(scope.files[file_id])
        if not path.is_file():
            raise FileNotFoundError('所选文件已移动或删除')
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('所选文件已超过 2 MB')
        return path.read_text(encoding='utf-8-sig')

    async def write_report(content: str):
        scope = app_task_scope.get()
        if not scope or 'app_write_report' not in scope.tools or not scope.record_file:
            raise PermissionError('此任务未请求文件产物')
        directory = Path(scope.output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        import uuid
        path = directory / f'报告-{uuid.uuid4().hex[:8]}.md'
        path.write_text(content, encoding='utf-8')
        reference = scope.record_file(str(path))
        scope.artifacts.append(str(path))
        from app.runtime.todo_context import get_todo_runtime
        runtime = get_todo_runtime()
        if runtime:
            runtime.bus.emit({'type': 'artifact.file', 'task_id': runtime.task_id, 'path': str(path)})
        return {**reference, 'status': 'created', 'path': str(path)}

    return [
        StructuredTool.from_function(coroutine=read_file, name='app_read_file', args_schema=ReadFile,
                                    description='读取用户为本次业务任务选择的文本文件，使用文件引用 ID。'),
        StructuredTool.from_function(coroutine=write_report, name='app_write_report', args_schema=WriteReport,
                                    description='将完整报告内容保存为新的 Markdown 文件并返回可找回的文件引用。'),
    ]
