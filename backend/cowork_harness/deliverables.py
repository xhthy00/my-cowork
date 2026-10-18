"""Keep complete HTML deliverables visible and request real host-backed writes."""
import re

from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def current_messages(messages):
    start = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=0)
    # Delivery reminders are HumanMessages too; retain the current turn's HTML.
    while start > 0 and str(messages[start].content).startswith('[HTML delivery]'):
        start = max((i for i in range(start) if isinstance(messages[i], HumanMessage)), default=0)
    return messages[start:]


def html_documents(messages):
    documents = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        text = re.sub(r'<think>[\s\S]*?</think>', '', message.text, flags=re.I)
        text = re.sub(r'<think>[\s\S]*$', '', text, flags=re.I)
        for source in re.findall(r'```html?\s*\n([\s\S]*?)\n```', text, flags=re.I):
            source = source.strip()
            if re.search(r'<html\b', source, re.I) and re.search(r'</html\s*>\s*$', source, re.I) and source not in documents:
                documents.append(source)
    return documents


def html_write_calls(messages, document):
    return [call for message in messages if isinstance(message, AIMessage) for call in message.tool_calls
            if call['name'] in {'fs_write', 'fs.write'} and document in str(call['args'].get('content', ''))]


def saved_html(messages, document):
    calls = {call['id'] for call in html_write_calls(messages, document)}
    return any(isinstance(message, ToolMessage) and message.tool_call_id in calls
               and message.status != 'error' and re.match(r'Wrote\s+\d+\s+characters\s+to\s+', message.text, re.I)
               for message in messages)


def preserve_html(messages, summary):
    """A final acknowledgement must not erase an earlier unsaved document."""
    messages = current_messages(messages)
    missing = [source for source in html_documents(messages)
               if source not in summary and not saved_html(messages, source)]
    if not missing:
        return summary
    return '已生成完整 HTML 内容，但尚未确认保存为文件，暂不能作为文件预览。\n\n' + '\n\n'.join(
        '```html\n' + source + '\n```' for source in missing)


class EnsureHtmlFile(AgentMiddleware):
    """Use official graph routing to finish an explicitly requested HTML file."""
    def __init__(self, writer):
        self.writer = writer
        self.attempts = 0

    @hook_config(can_jump_to=['model'])
    async def aafter_model(self, state, runtime):
        messages = current_messages(state['messages'])
        if not self.writer or not messages or getattr(messages[-1], 'tool_calls', None):
            return None
        requests = '\n'.join(m.text for m in messages if isinstance(m, HumanMessage)
                             or isinstance(m, ToolMessage) and m.name == 'ask_human')
        if not re.search(r'html[^\n]{0,30}(?:报告|文件|report)|(?:报告|文件|report)[^\n]{0,30}html', requests, re.I):
            return None
        documents = html_documents(messages)
        # A denied or failed write must not prompt the same operation repeatedly.
        if not documents or all(html_write_calls(messages, source) for source in documents) or self.attempts >= 2:
            return None
        self.attempts += 1
        return {'messages': [HumanMessage(content=(
            '[HTML delivery] 用户要求的是 HTML 报告文件。完整 HTML 已在本轮消息中，但尚未通过写入工具保存。'
            f'当前可用工具包含 {self.writer}；请调用它将完整 HTML 原样保存到真实工作目录，遵守宿主授权。'
            '必须收到成功写入结果后再交付绝对路径；不要让用户自行复制保存，也不要只更新步骤就宣称文件已交付。'
        ))], 'jump_to': 'model'}
