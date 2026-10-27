"""Deterministic structure checks for files returned as deliverables."""
import json
import re
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


def requested_formats(text):
    """Recognize an explicit output format after a generation/conversion verb."""
    names = {'word': {'.docx', '.doc'}, 'docx': {'.docx'}, 'pdf': {'.pdf'},
             'ppt': {'.pptx', '.ppt'}, 'pptx': {'.pptx'}, 'excel': {'.xlsx', '.xls'},
             'xlsx': {'.xlsx'}, 'html': {'.html', '.htm'}, 'markdown': {'.md'}, 'csv': {'.csv'}}
    for match in re.finditer(r'(?:生成|创建|制作|导出|输出|转成|转为|转换成|转换为|保存为|做成|写一份|做一份|generate\b|create\b|export\b|save as\b)([^\n]{0,32})', text, re.I):
        format_name = re.search(r'(?<![a-z])(word|docx|pdf|pptx?|excel|xlsx|html|markdown|csv)(?![a-z])', match[1], re.I)
        if format_name:
            return names[format_name[1].lower()]
    return set()


def validate_deliverable(path):
    target = Path(path)
    try:
        if target.stat().st_size == 0:
            return "交付文件为空"
        extension = target.suffix.lower()
        part = {'.docx': 'word/document.xml', '.pptx': 'ppt/presentation.xml',
                '.xlsx': 'xl/workbook.xml'}.get(extension)
        if part:
            with ZipFile(target) as archive:
                for name in ('[Content_Types].xml', part):
                    ElementTree.fromstring(archive.read(name))
                if archive.testzip() is not None:
                    return "Office 文件校验失败"
        elif extension == '.pdf':
            with target.open('rb') as source:
                if not source.read(8).startswith(b'%PDF-'):
                    return "PDF 文件头无效"
                source.seek(max(0, target.stat().st_size - 4096))
                if b'%%EOF' not in source.read():
                    return "PDF 文件未完整写入"
        elif extension == '.json':
            json.loads(target.read_text(encoding='utf-8-sig'))
    except Exception as exc:
        return "交付文件结构无效：" + str(exc)
    return None
