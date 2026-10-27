"""Conservative fast path for greetings and short explanatory questions."""
import re


def planning_required(text):
    value = text.strip()
    if re.fullmatch(r"(?:你好|您好|早上好|晚上好|谢谢|感谢|再见|hi|hello|thanks)[！!。.?？\s]*", value, re.I):
        return False
    if len(value) <= 200 and re.match(r"^(?:解释|介绍|什么是|为什么|what is\b|explain\b)", value, re.I):
        if not re.search(r"附件|文件|生成|创建|修改|保存|搜索|检索|最新|查询|运行|执行|删除|发送|报告|file|create|write|search|run|delete|send", value, re.I):
            return False
    return True
