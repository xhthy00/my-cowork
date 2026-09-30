#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_graph.py — 项目知识图谱构建/查询工具（dev-expert）。

正则抽取，结果写盘 {root}/.ai-memory/knowledge-graph/{graph.json,meta.json,symbols.json,graph.md}（不进 LLM 上下文）。
边类型：include/use/autoload/extends/template/tpimport/import/cssimport/asset/calls（跨 PHP/JS/TS/Java/Py/CSS/HTML 多语言）。
查询：--query <file|symbol> [--direction up|down|both] [--depth N] 裁剪子图（默认 2 跳，MAX_NODES=80）。
--query 入口先比对 mtime+内容哈希做新鲜度检测，过期则全量重建（v1 增量=全量重抽）。
约束：graph.md 仅人类兜底（agent 不加载）；符号孤儿检测占位未实现（留口）；LSP 仅记录可用性、抽取仍走正则（留口）；纯 v1 正则、无 AST/tree-sitter。
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

# ---------- 默认排除目录（规划 §5.6 #7） ----------
DEFAULT_EXCLUDE_DIRS = {
    # 依赖/构建产物
    'vendor', 'node_modules', 'dist', 'build', '__pycache__', '.cache',
    # 版本控制（避免抽 .git/.hg/.svn 内部文件）
    '.git', '.hg', '.svn',
    # 图谱产物自身（避免自引用重遍历）
    '.ai-memory',
    # 各 IDE / 编辑器项目级元数据目录
    '.codebuddy',   # CodeBuddy
    '.vscode',      # VS Code
    '.idea',        # JetBrains
    '.claude',      # Claude Code
    '.cursor',      # Cursor
    '.zed',         # Zed
    '.fleet',       # JetBrains Fleet
    '.sublime',     # Sublime Text
    # 国内 AI IDE
    '.trae',        # Trae
    '.qoder',       # Qoder / 通义灵码
    # 其他主流 IDE
    '.windsurf',    # Windsurf
    '.codeium',     # Codeium
    '.atom',        # Atom
    '.brackets',    # Brackets
    '.vs',          # Visual Studio
    '.metadata',    # Eclipse
    '.settings',    # Eclipse
    '.gradle',      # Gradle
    'nbproject',    # NetBeans
    'target',       # Maven / Eclipse 构建产物
}

# 运行时排除集（由 init_exclude_dirs 在 main 开头初始化，合并默认 + .graphignore + --exclude）
_EXCLUDE_DIRS = set(DEFAULT_EXCLUDE_DIRS)


def load_exclude_dirs(root, extra=None):
    """合并默认排除 + .graphignore + CLI --exclude。

    .graphignore 格式：每行一个目录名（不含路径分隔符），# 开头为注释，空行忽略。
    """
    dirs = set(DEFAULT_EXCLUDE_DIRS)
    gi = os.path.join(root, '.graphignore')
    if os.path.isfile(gi):
        try:
            with open(gi, encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        dirs.add(line.rstrip('/\\'))
        except Exception:
            pass
    if extra:
        dirs.update(x.strip().rstrip('/\\') for x in extra.split(',') if x.strip())
    return dirs

# ---------- 纳入图谱的源码扩展名（遍历与新鲜度检测须一致） ----------
SRC_EXTS = ('.php', '.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx',
            '.py', '.java', '.htm', '.html', '.css', '.scss', '.less')

# ---------- 抽取正则（PHP/JS，v1 一等支持） ----------
RE_REQ_STMT = re.compile(r"(?:require|include)(?:_once)?\s*\(?\s*(.+?)\s*\)?\s*;", re.I | re.S)
RE_STR = re.compile(r"['\"]([^'\"]+)['\"]")
RE_DYNAMIC_MARK = re.compile(r"\$\w+")  # 变量拼路径（如 $base . '/x'）→ 抽不出
RE_CLASS = [
    re.compile(r"(?:class|interface|trait|enum)\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w\s,]+))?"),
    re.compile(r"(?:public\s+|private\s+|protected\s+)?function\s+(\w+)\s*\("),
]
# ---------- 命名空间 / use（覆盖 composer PSR-4 框架：ThinkPHP/易优/迅睿/FastAdmin/Laravel） ----------
RE_NAMESPACE = re.compile(r"^\s*namespace\s+([\w\\]+)\s*;", re.M)
RE_USE = re.compile(r"^\s*use\s+([\w\\]+)(?:\s+as\s+(\w+))?\s*;", re.M)
RE_NEW_FQN = re.compile(r"new\s+\\?([\w\\]+)\s*\(")            # new \App\X 或 new App\X
# ---------- 非 PHP 语言模块导入（覆盖 Django/Flask/Spring/Express/NestJS/Next/React/Vue/Angular/Strapi） ----------
RE_PY_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import\s+\w+|import\s+([\w.]+))", re.M)
RE_JS_REQUIRE = re.compile(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
RE_JS_IMPORT = re.compile(r"import\s+(?:[^'\"(]*?\s+from\s+)?['\"]([^'\"]+)['\"]")
RE_JS_DYNAMIC_IMPORT = re.compile(r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
RE_JAVA_IMPORT = re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)\s*;", re.M)
RE_JAVA_PKG = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
# ---------- ThinkPHP 显式类库导入（TP3/TP5 官方机制，thinkphp.cn/info/126） ----------
RE_TP_IMPORT = re.compile(r"(import|vendor|Loader::import)\s*\(\s*['\"]([^'\"]+)['\"]")


RE_TPL_INCLUDE = re.compile(
    r"\{\s*[a-z]*:?include\b[^}]*?\bfile\s*=\s*['\"]([^'\"]+)['\"]", re.I)
RE_TPL_REQUIRE = re.compile(r"template\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")  # template('x')
# ---------- CSS / HTML 资源依赖（前端样式与脚本依赖） ----------
RE_CSS_IMPORT = re.compile(r"@import\s+(?:url\()?\s*['\"]?([^'\"()\s;]+)['\"]?\s*\)?\s*;", re.I)
RE_HTML_LINK = re.compile(r"<link\b[^>]*\bhref\s*=\s*['\"]([^'\"]+)['\"]", re.I)
RE_HTML_SCRIPT = re.compile(r"<script\b[^>]*\bsrc\s*=\s*['\"]([^'\"]+)['\"]", re.I)




def _resolve_const_include(head, lit, rel, const_table, root):
    """解析 require 表达式里的常量前缀拼接：CONST . 'lit' / CONST.CONST . 'lit' / 纯 CONST。

    逐 token 调 resolve_const 解析常量值，路径段斜杠拼接 + 绝对/相对归一；返回相对 root 的 rel。
    常量未定义/循环/含变量 → None（交由调用方落字面量兜底）。
    """
    lit = lit or ''
    base = ''
    ok = True
    if re.match(r"^[A-Z_][A-Z0-9_]*$", head):
        base = resolve_const(head, const_table, root) if head in const_table else None
        if base is None:
            ok = False
    else:  # 常量链 CONST . CONST . ...
        for tok in re.split(r"\s*\.\s*", head):
            rb = resolve_const(tok, const_table, root) if tok in const_table else None
            if rb is None:
                ok = False
                break
            base = (base.rstrip('/') + '/' + rb.lstrip('/')) if base else rb
    if not ok:
        return None
    base = os.path.normpath(base) if base else ''
    if lit:
        lit2 = lit.lstrip('/')
        if base and (base.startswith('/') or re.match(r'^[A-Za-z]:', base) or os.path.isabs(base)):
            target = os.path.normpath(base.rstrip('/') + '/' + lit2)
        else:
            target = os.path.normpath(os.path.join(base, lit2)) if base else os.path.normpath(lit2)
    else:
        target = base
    if base and not (target.startswith('/') or re.match(r'^[A-Za-z]:', target) or os.path.isabs(target)):
        target = os.path.normpath(os.path.join(root, target))
    return target


def read_text(path):
    """读文本文件：UTF-8 BOM 自动剥 + UTF-8 解码失败回退 GBK。

    解决帝国 CMS 等 GBK 编码文件的中文路径/注释抽取漏报（errors='ignore' 会丢字节致路径截断）。
    """
    with open(path, 'rb') as f:
        raw = f.read()
    if raw.startswith(b'\xef\xbb\xbf'):
        raw = raw[3:]
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return raw.decode('gbk')
        except UnicodeDecodeError:
            return raw.decode('utf-8', errors='ignore')


def strip_php_comments(text):
    """B2：抽取 include 前剥离 PHP 注释，避免注释/死代码被当真边。

    启发式（非解析器）：
    - 块注释：字符串感知状态机剥离，跳过字符串内的 /* */（4c 增强，避免误删 $sql="/* x */"）
    - heredoc/nowdoc：跳过 heredoc 内的 # //（4b 增强，避免误剥 SQL 内 #）
    - 行注释：// 和 #，仅当注释符前为行首空白或语句结束符才视为注释
    已知局限：跨行字符串状态可能误判（罕见）。
    """
    # 1) 块注释：字符串感知状态机，跳过字符串内的 /* */
    out_chars = []
    in_str = False
    quote = ''
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            if ch == '\\' and i + 1 < n:
                out_chars.append(text[i:i + 2])
                i += 2
                continue
            out_chars.append(ch)
            if ch == quote:
                in_str = False
            i += 1
        else:
            if ch in ('"', "'"):
                in_str = True
                quote = ch
                out_chars.append(ch)
                i += 1
            elif ch == '/' and i + 1 < n and text[i + 1] == '*':
                end = text.find('*/', i + 2)
                if end == -1:
                    nl = text.find('\n', i)
                    if nl == -1:
                        nl = n
                    out_chars.append('\n' * text[i:nl].count('\n'))
                    i = nl
                else:
                    out_chars.append('\n' * text[i:end + 2].count('\n'))
                    i = end + 2
            else:
                out_chars.append(ch)
                i += 1
    text = ''.join(out_chars)
    # 2) 行注释：跳过 heredoc 内的 # //，仅当注释符前为行首空白或语句结束符才视为注释
    out = []
    in_heredoc = False
    heredoc_tag = ''
    for line in text.split('\n'):
        if in_heredoc:
            out.append(line)
            if line.strip().rstrip(';,').rstrip() == heredoc_tag:
                in_heredoc = False
            continue
        m = re.match(r'^\s*<<<?\s*([\'"]?)(\w+)\1', line)
        if m:
            in_heredoc = True
            heredoc_tag = m.group(2)
            out.append(line)
            continue
        # 找行注释起点：遍历字符，遇未闭合引号内的 // # 跳过
        in_s = False
        quote = ''
        i = 0
        n = len(line)
        cut = -1
        while i < n:
            ch = line[i]
            if in_s:
                if ch == '\\':
                    i += 2
                    continue
                if ch == quote:
                    in_s = False
            else:
                if ch in ('"', "'"):
                    in_s = True
                    quote = ch
                elif ch == '#':
                    cut = i
                    break
                elif ch == '/' and i + 1 < n and line[i + 1] == '/':
                    cut = i
                    break
            i += 1
        if cut >= 0:
            # 行注释符前需为行首空白或语句结束符，否则视为字符串/URL 内
            head = line[:cut].rstrip()
            if head == '' or head.endswith((';', '}', '{', ')', '?')):
                out.append(line[:cut])
                continue
        out.append(line)
    return '\n'.join(out)


def extract_includes(text, rel, root, const_table=None):
    """提取 include/require 目标（覆盖帝国/易优/迅睿/ThinkPHP 等 CMS）。

    支持：字面量/相对路径、__DIR__/dirname 拼接、define() 常量链（递归解 RHS）、变量拼路径（动态抽不出跳过）。
    常量无法静态解析（未定义/循环/含变量）→ 落字面量兜底，不跳过（避免误边）。
    B2：PHP 文件抽取前先剥离注释（见 strip_php_comments）。
    """
    text = strip_php_comments(text)
    const_table = const_table or {}
    includes = []
    for m in RE_REQ_STMT.finditer(text):
        expr = m.group(1).strip()
        # 1) __DIR__ / dirname(...) 拼接（保持原行为）
        if '__DIR__' in expr or 'dirname(' in expr:
            sm = RE_STR.search(expr)
            if sm:
                raw = sm.group(1)
                target = os.path.normpath(os.path.join(os.path.dirname(rel), raw.lstrip('/')))
                includes.append(target)
            continue
        # 2) define() 常量前缀拼接：CONST . 'lit' / 链 / 纯 CONST（_resolve_const_include 提取，语义 1:1 保留）。
        # 刻意不复用 _resolve_const_rhs：其路径段拼接不加斜杠，多常量链(A.B)会生成 e/asubx.php 错误路径。
        cm = re.match(
            r"^((?:[A-Z_][A-Z0-9_]*)(?:\s*\.\s*[A-Z_][A-Z0-9_]*)*)"
            r"\s*\.\s*['\"]([^'\"]*)['\"]$", expr) or \
            re.match(r"^([A-Z_][A-Z0-9_]*)$", expr)
        if cm:
            target = _resolve_const_include(cm.group(1),
                                            cm.group(2) if len(cm.groups()) >= 2 else '',
                                            rel, const_table, root)
            if target is not None:
                includes.append(target)
                continue
            # 常量未定义或无法静态解析 → 落到下方字面量兜底（旧行为），不跳过
        # 3) 字面量 / 相对路径（原逻辑）
        sm = RE_STR.search(expr)
        if not sm:
            continue
        raw = sm.group(1)
        # 变量拼路径（如 $base . '/x'）→ 动态，正则抽不出，跳过（规划漏抽边界）
        if RE_DYNAMIC_MARK.search(expr):
            continue
        if raw.startswith('/') or re.match(r'^[A-Za-z]:', raw):
            target = os.path.normpath(raw)
        elif raw.startswith('./') or raw.startswith('../'):
            target = os.path.normpath(os.path.join(os.path.dirname(rel), raw))
        else:
            # 无前缀 include_path 风格，回退 root
            target = os.path.normpath(os.path.join(os.path.dirname(rel), raw))
            if not os.path.exists(target):
                target = os.path.normpath(os.path.join(root, raw))
        includes.append(target)
    return includes


def file_hash(path):
    """返回文件 md5；无读权限/不存在等异常返回 None（B4：避免 need_rebuild/build 因单文件不可读而整体崩溃）。"""
    try:
        h = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _safe_mtime(path):
    """返回文件 mtime；异常返回 None（need_rebuild 的廉价新鲜度前置过滤用）。"""
    try:
        return os.path.getmtime(path)
    except Exception:
        return None


def detect_lsp(root):
    """运行时 LSP 探测（仅记录可用性，v1 抽取仍走正则）。"""
    import shutil
    avail = {}
    # D-2：统一用 shutil.which 探测（移除跨平台脆弱的 os.system 同步阻塞）；未命中 → False（仅可用性记录）。
    try:
        avail['php'] = bool(shutil.which('intelephense') or shutil.which('phpactor'))
    except Exception:
        avail['php'] = False
    # 其他语言默认 False（本机实测）
    for lang in ('js', 'python', 'java', 'go'):
        avail[lang] = False
    return avail


# ---------- define() 常量前缀解析（覆盖国内 CMS/框架） ----------
RE_DEFINE = re.compile(
    r"define\s*\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*,\s*(.+?)\s*\)\s*;",
    re.I | re.S)
RE_CONST_DECL = re.compile(
    r"(?:public\s+|private\s+|protected\s+|final\s+|static\s+)*"
    r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+?)\s*;", re.I)


def extract_defines(text, rel):
    """抽取本文件 define()/const 常量 -> {NAME: (raw_rhs, defining_rel)}。"""
    out = {}
    for m in RE_DEFINE.finditer(text):
        out[m.group(1)] = (m.group(2).strip(), rel)
    for m in RE_CONST_DECL.finditer(text):
        out[m.group(1)] = (m.group(2).strip(), rel)
    return out


def _resolve_segment(seg, const_table, root, seen):
    """解析单个拼接段：字面量 / dirname() / 裸常量名。无法静态解析返回 None。"""
    seg = seg.strip()
    if not seg:
        return ''
    sm = re.match(r"^['\"]([^'\"]*)['\"]$", seg)
    if sm:
        return sm.group(1)
    dm = re.match(r"^dirname\(\s*(.*?)\s*\)$", seg)
    if dm:
        inner = _resolve_segment(dm.group(1), const_table, root, seen)
        if inner is None:
            return None
        return os.path.dirname(inner)
    if re.match(r"^[A-Z_][A-Z0-9_]*$", seg):
        return resolve_const(seg, const_table, root, seen)
    return None  # 含 $ / 函数调用等无法静态解析


def _resolve_const_rhs(raw, defining_rel, const_table, root, seen):
    """解析常量 RHS：字面量 / . 拼接链；__DIR__/__FILE__ 用 defining_rel 替换。"""
    raw = raw.strip()
    sm = re.match(r"^['\"]([^'\"]*)['\"]$", raw)
    if sm:
        return sm.group(1)
    work = raw
    if '__DIR__' in work:
        work = work.replace('__DIR__',
                            "'" + os.path.normpath(os.path.join(root,
                                os.path.dirname(defining_rel))).replace(os.sep, '/') + "'")
    if '__FILE__' in work:
        work = work.replace('__FILE__',
                            "'" + os.path.normpath(os.path.join(root,
                                defining_rel)).replace(os.sep, '/') + "'")
    # 按 ` . `（带空格的拼接运算符）切分，避免误切字符串内的点（如 .php）
    parts = re.split(r"\s+\.\s+", work)
    res = ''
    for p in parts:
        if p.strip() == '':
            continue
        seg = _resolve_segment(p, const_table, root, seen)
        if seg is None:
            return None
        res += seg
    if res:
        res = os.path.normpath(res)
        # 解析结果若落在 root 内（绝对），转回相对路径，保持图谱可移植
        if os.path.isabs(res) and res.startswith(os.path.abspath(root)):
            res = os.path.relpath(res, os.path.abspath(root)).replace(os.sep, '/')
            if res == '.':
                res = ''  # 解析结果恰为项目根 → 空串，避免拼接出 '.extend' 这类错误路径
        return res
    return None


def resolve_const(name, const_table, root, seen=None):
    """递归解析一个 define 常量的值为真实路径片段；循环/未定义/含变量返回 None。"""
    if seen is None:
        seen = set()
    if name in seen:
        return None
    entry = const_table.get(name)
    if not entry:
        return None
    raw, drel = entry
    seen.add(name)
    return _resolve_const_rhs(raw, drel, const_table, root, seen)


def parse_composer(root):
    """解析 composer.json 的 autoload（psr-4 / psr-0 / files / classmap）。

    返回 {psr4: {prefix: dir}, psr0: {prefix: dir}, files: [rel...], classmap: [dir...]}。
    国内 ThinkPHP/易优/迅睿/FastAdmin/Laravel 等框架靠此把命名空间映射到文件。
    """
    out = {'psr4': {}, 'psr0': {}, 'files': [], 'classmap': []}
    cj = os.path.join(root, 'composer.json')
    if not os.path.isfile(cj):
        return out
    try:
        data = json.load(open(cj, encoding='utf-8', errors='ignore'))
    except Exception:
        return out
    al = data.get('autoload', {})
    for kind, key in (('psr4', 'psr-4'), ('psr0', 'psr-0')):
        for pref, d in (al.get(key) or {}).items():
            pref = pref.rstrip('/').rstrip('\\')  # A-1：剥尾部反斜杠，否则 fqn_to_file 的 pref+'\\' 拼接多一反斜杠致 startswith 永 False
            if isinstance(d, list):
                for x in d:
                    out[kind][pref] = x.rstrip('/').rstrip('\\')
            else:
                out[kind][pref] = d.rstrip('/').rstrip('\\')
    for f in (al.get('files') or []):
        out['files'].append(f)
    for cm in (al.get('classmap') or []):
        out['classmap'].append(cm)
    return out


def fqn_to_file(fqn, composer, root):
    """按 PSR-4 / PSR-0 把完全限定类名映射到文件路径；找不到返回 None。"""
    fqn = fqn.lstrip('\\')
    parts = fqn.split('\\')
    # PSR-4：最长前缀匹配
    for pref in sorted(composer['psr4'], key=len, reverse=True):
        if fqn == pref or fqn.startswith(pref + '\\'):
            rest = fqn[len(pref):].lstrip('\\').split('\\')
            d = composer['psr4'][pref]
            rel = os.path.normpath(os.path.join(d, *rest)) + '.php'
            if os.path.isfile(os.path.join(root, rel)):
                return rel.replace(os.sep, '/')
            return rel.replace(os.sep, '/')  # 即便文件暂缺也返回预期路径（标悬空）
    # PSR-0：每段映射（\ 和 _ 都转目录分隔符，PSR-0 规范）
    for pref in sorted(composer['psr0'], key=len, reverse=True):
        if fqn == pref or fqn.startswith(pref + '\\'):
            rest = fqn[len(pref):].lstrip('\\').replace('\\', '/').replace('_', '/')
            rest_parts = [p for p in rest.split('/') if p]
            d = composer['psr0'][pref]
            rel = os.path.normpath(os.path.join(d, *rest_parts)) + '.php'
            if os.path.isfile(os.path.join(root, rel)):
                return rel.replace(os.sep, '/')
            return rel.replace(os.sep, '/')
    return None


def resolve_module(spec, lang, rel, root):
    """按语言把 import 说明符解析为项目内文件 rel（或 None）：Python/JS(ts)/Java。
    相对路径优先相对源文件；裸说明符回退 node_modules / 包根启发式。
    """
    spec = spec.strip()
    if not spec:
        return None
    # rel 在 Windows 下是 '/' 分隔，os.path.dirname 不认 '/'，须转成本地分隔符
    rel_native = rel.replace('/', os.sep)
    src_dir = os.path.dirname(rel_native)
    src_full = os.path.join(root, src_dir) if src_dir else root
    if lang == 'py':
        parts = spec.split('.')
        if parts and parts[0] == '':
            parts = parts[1:]  # 去前导点（.models）
        cands = []
        for base in (src_full, root):
            cands.append(os.path.join(base, *parts) + '.py')
            cands.append(os.path.join(base, *parts, '__init__.py'))
        for c in cands:
            if os.path.isfile(c):
                return os.path.relpath(c, root).replace(os.sep, '/')
        return None
    if lang in ('js', 'ts'):
        if spec.startswith('./') or spec.startswith('../'):
            base = os.path.normpath(os.path.join(src_full, spec))
            # 若说明符自身已带扩展名（./styles.css），优先按原样试
            if os.path.splitext(spec)[1]:
                if os.path.isfile(base):
                    return os.path.relpath(base, root).replace(os.sep, '/')
            for ext in ('.js', '.ts', '.jsx', '.tsx', '.mjs', '.cjs', '.json', '.css', '.scss', '.less'):
                c = base + ext
                if os.path.isfile(c):
                    return os.path.relpath(c, root).replace(os.sep, '/')
            for idx in ('index.js', 'index.ts', 'index.jsx', 'index.tsx'):
                c = os.path.join(base, idx)
                if os.path.isfile(c):
                    return os.path.relpath(c, root).replace(os.sep, '/')
            return None
        # 裸说明符：node_modules 启发式
        nm_dirs = [os.path.join(root, 'node_modules')]
        if src_dir:
            nm_dirs.append(os.path.join(root, src_dir, 'node_modules'))
        for nm in (spec, spec.lstrip('@')):
            for top in nm_dirs:
                c = os.path.join(top, nm)
                for entry in ('index.js', 'index.ts', 'index.jsx', 'index.tsx', 'src/index.js', 'src/index.ts'):
                    if os.path.isfile(os.path.join(c, entry)):
                        return os.path.relpath(os.path.join(c, entry), root).replace(os.sep, '/')
        return None
    if lang == 'java':
        parts = spec.split('.')
        rest = parts[:-1] if spec.endswith('.*') else parts
        relp = os.path.normpath(os.path.join(*rest)) + '.java'
        c = os.path.join(root, relp)
        if os.path.isfile(c):
            return os.path.relpath(c, root).replace(os.sep, '/')
        # 包路径相对源码根（com/x/Y.java 可能位于 root 下任意 java/ 子目录），递归搜索
        for dp, _, fns in os.walk(root):
            if any(x in dp for x in _EXCLUDE_DIRS):
                continue
            cand = os.path.join(dp, relp)
            if os.path.isfile(cand):
                return os.path.relpath(cand, root).replace(os.sep, '/')
        return None
    return None


def resolve_tp_import(spec, root, const_table):
    """解析 ThinkPHP import()/vendor()/Loader::import()（官方规则 thinkphp.cn/info/126）。

    点号转目录；基库前缀映射（依赖项目定义的常量，经 resolve_const 解析）：
      Think.*   -> THINK_PATH/Lib/*           (去 Think 前缀，后缀 .class.php)
      ORG.*     -> EXTEND_PATH/Library/ORG/*  (保留 ORG 段，后缀 .class.php)
      Com.*     -> EXTEND_PATH/Library/Com/*  (保留 Com 段，后缀 .class.php)
      Vendor.*  -> VENDOR_PATH/*              (去 Vendor 前缀；vendor() 调用已补 Vendor.)
      @.*       -> APP_PATH/*                 (去 @ 前缀，后缀 .class.php)
      其它(项目类库,如 Common.Tool/MyApp.Action.User) -> APP_PATH/* 完整点路径（.class.php 优先，缺失回退 .php）
    别名导入(单段无点,如 import('rbac')) 需 alias.php 映射,静态难穷举,留口 None。
    """
    spec = spec.strip()
    if not spec or '.' not in spec:
        return None  # 别名/多参仅首参带点形式留口
    parts = spec.split('.')
    head = parts[0]
    if spec.startswith('@'):
        base = resolve_const('APP_PATH', const_table, root) or 'application'
        parts = parts[1:]                      # 去 @ 别名段
        suffix = '.class.php'
    elif head == 'Think':
        tp = resolve_const('THINK_PATH', const_table, root) or \
            resolve_const('LIB_PATH', const_table, root) or 'ThinkPHP'
        base = (tp.rstrip('/') + '/Lib') if tp else 'ThinkPHP/Lib'
        parts = parts[1:]                      # 去 Think 前缀
        suffix = '.class.php'
    elif head in ('ORG', 'Com'):
        ep = resolve_const('EXTEND_PATH', const_table, root) or 'Extend/Library'
        base = (ep.rstrip('/') + '/Library') if ep else 'Extend/Library'
        # 保留 ORG/Com 段（EXTEND_PATH/Library/ORG/...）；用首段精确匹配避免 Common 误命中 Com
        suffix = '.class.php'
    elif head == 'Vendor':
        vp = resolve_const('VENDOR_PATH', const_table, root) or 'Vendor'
        base = vp.rstrip('/') if vp else 'Vendor'
        parts = parts[1:]                      # 去 Vendor 前缀（base 已是 VENDOR_PATH）
        suffix = '.class.php'
    else:  # 项目/应用类库：完整点路径映射目录（Common.Tool 不会误命中 Com 前缀）
        base = resolve_const('APP_PATH', const_table, root) or 'application'
        suffix = '.class.php'
    if not base or not parts:
        return None
    relp = os.path.normpath(os.path.join(base, *parts)) + suffix
    c = os.path.join(root, relp)
    if os.path.isfile(c):
        return os.path.relpath(c, root).replace(os.sep, '/')
    # 项目类库非标准后缀回退 .php（import('X', APP_PATH, '.php') 形态）
    if suffix == '.class.php':
        c2 = os.path.join(root, os.path.normpath(os.path.join(base, *parts)) + '.php')
        if os.path.isfile(c2):
            return os.path.relpath(c2, root).replace(os.sep, '/')
    return None


def extract_file(path, root, const_table=None):
    """抽取单文件：返回 {includes, classes, calls, namespace, uses, tpl_includes}。"""
    text = ''
    try:
        text = read_text(path)
    except Exception:
        return {'includes': [], 'classes': [], 'calls': [], 'namespace': None,
                'uses': [], 'tpl_includes': []}
    rel = os.path.relpath(path, root).replace(os.sep, '/')
    # include/require 是 PHP 专属语法；其余语言走各自模块导入机制，禁止用 PHP 正则误抽（否则 JS `src:` 等成噪声边）。
    PHP_EXTS = ('.php', '.inc', '.phtml', '.php3', '.php4', '.php5')
    # B-?：符号抽取须在剥离 PHP 注释后进行（避免注释/死代码里的 `// class X` 被当真实符号生成假边）。
    # extract_includes 内部已自剥离；此处对非 include 的符号层统一前置剥离（仅 PHP 文件，非 PHP 仍用原文）。
    code = strip_php_comments(text) if rel.endswith(PHP_EXTS) else text
    includes = extract_includes(text, rel, root, const_table) if rel.endswith(PHP_EXTS) else []
    # PHP 专属符号抽取（namespace/use/class/function/calls/new/::/FQN/tpimport）仅对 PHP 运行；
    # 非 PHP 文件这些字段置空，禁止 .py/.js/.ts/.java 被 PHP 正则误抽污染符号表（ERR-006 同族）。
    if rel.endswith(PHP_EXTS):
        ns_m = RE_NAMESPACE.search(code)
        namespace = ns_m.group(1) if ns_m else None
        uses = [{'fqn': m.group(1), 'alias': m.group(2)} for m in RE_USE.finditer(code)]
        classes = []
        for m in RE_CLASS[0].finditer(code):
            cls = m.group(1)
            ext = m.group(2)
            impl = m.group(3)
            classes.append({'name': cls, 'line': code[:m.start()].count('\n') + 1,
                            'extends': ext, 'implements': impl})
        funcs = []
        for m in RE_CLASS[1].finditer(code):
            funcs.append(m.group(1))
        # calls：new X() / X::const（跨文件才记，规划 §4 敏感边约束）
        # 注：$obj->method() 抽不出类名（变量非类型，静态分析边界），属动态调用漏抽，
        #     由 G2' grep 复核兜底；保留 new/:: 两类可静态解析类名的调用。
        calls = []
        for m in re.finditer(r"new\s+(\w+)\s*\(", code):
            calls.append(m.group(1))
        for m in re.finditer(r"(\w+)::\w+", code):
            calls.append(m.group(1))
        # new \Ns\Class（框架类实例化，composer 自动加载）
        new_fqns = [m.group(1) for m in RE_NEW_FQN.finditer(code)]
        # ThinkPHP 显式类库导入 import()/vendor()/Loader::import()（TP3/TP5 官方机制）
        tp_imports = [(m.group(1), m.group(2)) for m in RE_TP_IMPORT.finditer(code)]
    else:
        namespace = None
        uses = []
        classes = []
        funcs = []
        calls = []
        new_fqns = []
        tp_imports = []
    # 模板 include 标签（帝国/Dede/Discuz/易优 模板依赖；CMS 模板标签非 PHP 语法，保留原扫描 text）
    tpl_includes = []
    for m in RE_TPL_INCLUDE.finditer(text):
        tpl_includes.append(m.group(1))
    for m in RE_TPL_REQUIRE.finditer(text):
        tpl_includes.append(m.group(1))
    # 非 PHP 语言模块导入（Django/Flask/Spring/React/Vue/...）
    lang = None
    if rel.endswith('.py'):
        lang = 'py'
    elif rel.endswith(('.js', '.jsx', '.mjs', '.cjs')):
        lang = 'js'
    elif rel.endswith(('.ts', '.tsx')):
        lang = 'ts'
    elif rel.endswith('.java'):
        lang = 'java'
    module_imports = []
    if lang == 'py':
        for m in RE_PY_IMPORT.finditer(text):
            module_imports.append(m.group(1) or m.group(2))
    elif lang in ('js', 'ts'):
        for m in RE_JS_REQUIRE.finditer(text):
            module_imports.append(m.group(1))
        for m in RE_JS_IMPORT.finditer(text):
            module_imports.append(m.group(1))
        for m in RE_JS_DYNAMIC_IMPORT.finditer(text):
            module_imports.append(m.group(1))
    elif lang == 'java':
        java_pkg = RE_JAVA_PKG.search(text)
        for m in RE_JAVA_IMPORT.finditer(text):
            module_imports.append(m.group(1))
    # CSS @import 依赖（指向其它样式文件，真实样式级联依赖）
    css_imports = []
    if rel.endswith(('.css', '.scss', '.less')):
        for m in RE_CSS_IMPORT.finditer(text):
            css_imports.append(m.group(1))
    # HTML <link href> / <script src> 资源依赖（样式表与脚本，排除图片等噪声）
    # .php 亦输出 HTML（CMS 模板普遍在 .php 中直接写 <link>/<script>）
    html_assets = []
    if rel.endswith(('.php', '.htm', '.html')):
        for m in RE_HTML_LINK.finditer(text):
            if m.group(1).endswith(('.css', '.scss', '.less', '.js', '.jsx',
                                     '.ts', '.tsx', '.mjs', '.cjs')):
                html_assets.append(m.group(1))
        for m in RE_HTML_SCRIPT.finditer(text):
            if m.group(1).endswith(('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs')):
                html_assets.append(m.group(1))
    return {'rel': rel, 'includes': includes, 'classes': classes,
            'funcs': funcs, 'calls': calls, 'namespace': namespace,
            'uses': uses, 'tpl_includes': tpl_includes, 'new_fqns': new_fqns,
            'lang': lang, 'module_imports': module_imports, 'tp_imports': tp_imports,
            'css_imports': css_imports, 'html_assets': html_assets}


def _acquire_lock(root, max_wait=10, stale_timeout=60):
    """获取构建锁，防多进程并发构建。等待 max_wait 秒，超 stale_timeout 的锁视为僵尸强制接管。"""
    lock_path = os.path.join(root, '.ai-memory', 'knowledge-graph', '.lock')
    for _ in range(max_wait):
        if os.path.isfile(lock_path):
            try:
                age = time.time() - os.path.getmtime(lock_path)
                if age > stale_timeout:
                    break  # 僵尸锁，强制接管
            except Exception:
                break
            time.sleep(1)
        else:
            break
    try:
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        with open(lock_path, 'w') as f:
            f.write(str(os.getpid()))
        return True
    except Exception:
        return False


def _release_lock(root):
    """释放构建锁。"""
    lock_path = os.path.join(root, '.ai-memory', 'knowledge-graph', '.lock')
    try:
        if os.path.isfile(lock_path):
            os.remove(lock_path)
    except Exception:
        pass


def build(root):
    """全量构建。返回 (graph, meta, symbols)。"""
    out_dir = os.path.join(root, '.ai-memory', 'knowledge-graph')
    _acquire_lock(root)  # 并发锁：防多进程同时构建（超 60s 僵尸锁强制接管）
    os.makedirs(out_dir, exist_ok=True)
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS
                       and not d.startswith('.')]
        for fn in filenames:
            if fn.endswith(SRC_EXTS):
                files.append(os.path.join(dirpath, fn))
    file_list = [os.path.relpath(p, root).replace(os.sep, '/') for p in files]
    lsp = detect_lsp(root)
    # 常量预扫描（支持 define()/const 前缀拼路径的国内 CMS/框架）
    CONST_TABLE = {}
    for f, p in sorted(zip(file_list, files)):  # 常量预扫描按 rel 排序，避免同常量多定义时解析随遍历顺序漂移（B-1）
        try:
            txt = read_text(p)
        except Exception:
            continue
        for nm, val in extract_defines(txt, f).items():
            CONST_TABLE[nm] = val  # 后定义覆盖
    extracted = {f: extract_file(p, root, CONST_TABLE) for f, p in zip(file_list, files)}
    COMPOSER = parse_composer(root)

    nodes = {}      # rel -> {type, classes, funcs}
    edges = []      # {from, to, kind}
    edge_keys = set()  # 边去重键集合（B-4）：(from, to, kind) 精确去重，避免重复 require 产生重复边
    symbols = {}    # name -> {file, line}
    fqn_symbols = {}  # FQN -> file（命名空间类，覆盖 composer 框架）
    dangling = []
    orphan_symbols = []
    include_total = 0
    include_valid = 0

    # 第一轮：建符号表（含命名空间 FQN）
    for rel, ex in extracted.items():
        ns = ex['namespace']
        for c in ex['classes']:
            symbols[c['name']] = {'file': rel, 'line': c['line']}
            if ns:
                fqn_symbols[(ns + '\\' + c['name']).lower()] = rel
        nodes[rel] = {'file': rel, 'classes': [c['name'] for c in ex['classes']],
                      'funcs': ex['funcs']}

    def add_edge_if_exists(rel, target_rel, kind, symbol=None):
        """已存在则加 include 边；否则记悬空（不进图）。"""
        nonlocal include_total, include_valid, edge_keys
        # define() 常量链解析可能产生项目内绝对路径 → 归一为相对 rel（保证图谱可移植、query 可遍历）
        if os.path.isabs(target_rel):
            normed = os.path.normpath(target_rel)  # 统一分隔符后再判项目内（Windows 下正斜杠/反斜杠）
            if normed.startswith(os.path.abspath(root)):
                target_rel = os.path.relpath(normed, os.path.abspath(root)).replace(os.sep, '/')
            else:
                return  # 项目外绝对路径，不纳入图谱
        if kind == 'include':
            include_total += 1
        if target_rel and os.path.exists(os.path.join(root, target_rel)):
            if any(d in target_rel.split('/') for d in _EXCLUDE_DIRS):
                return
            if kind == 'include':
                include_valid += 1
            key = (rel, target_rel, kind)
            if key in edge_keys:
                return
            edge_keys.add(key)
            e = {'from': rel, 'to': target_rel, 'kind': kind}
            if symbol:
                e['symbol'] = symbol
            edges.append(e)
        else:
            dangling.append({'from': rel, 'raw': target_rel, 'resolved': target_rel,
                             'base': 'ns' if kind != 'include' else 'src'})

    for rel, ex in extracted.items():
        for c in ex['classes']:
            if c.get('extends'):
                ext = c['extends']
                # extends 可能是短名(同文件/全局)或 FQN
                tgt = None
                if '\\' in ext:
                    tgt = fqn_symbols.get(ext.lower()) or fqn_to_file(ext, COMPOSER, root)
                elif ext in symbols:
                    tgt = symbols[ext]['file']
                if tgt:
                    add_edge_if_exists(rel, tgt, 'extends')
        for inc in ex['includes']:
            add_edge_if_exists(rel, inc.replace(os.sep, '/'), 'include')
        # use 导入解析（composer PSR-4 框架核心机制）
        for u in ex['uses']:
            fqn = u['fqn']
            tgt = fqn_symbols.get(fqn.lower()) or fqn_to_file(fqn, COMPOSER, root)
            if tgt:
                add_edge_if_exists(rel, tgt, 'use', symbol=fqn)
        # new \Ns\Class / \Ns\Class:: （框架类实例化/静态调用）
        for fqn in ex['new_fqns']:
            tgt = fqn_symbols.get(fqn.lower()) or fqn_to_file(fqn, COMPOSER, root)
            if tgt and tgt != rel:
                add_edge_if_exists(rel, tgt, 'autoload', symbol=fqn)
        # ThinkPHP import()/vendor() 显式类库导入（TP3/TP5，官方 thinkphp.cn/info/126）
        for func, spec in ex['tp_imports']:
            if func == 'vendor':
                spec = 'Vendor.' + spec  # vendor() 说明符隐含 Vendor. 前缀
            tgt = resolve_tp_import(spec, root, CONST_TABLE)
            if tgt and tgt != rel:
                add_edge_if_exists(rel, tgt, 'tpimport', symbol=spec)
        # 非 PHP 语言模块导入（Django/Flask/Spring/React/Vue/Angular/Next/Nest/Strapi）
        if ex['lang']:
            for spec in ex['module_imports']:
                tgt = resolve_module(spec, ex['lang'], rel, root)
                if tgt and tgt != rel:
                    add_edge_if_exists(rel, tgt, 'import', symbol=spec)
        # 模板 {include file=}（帝国/Dede/Discuz/易优 模板依赖）
        for tpl in ex['tpl_includes']:
            trel = os.path.normpath(tpl.lstrip('/'))
            if not (trel.startswith('/') or re.match(r'^[A-Za-z]:', trel)):
                trel = os.path.normpath(os.path.join(os.path.dirname(rel), trel))
            add_edge_if_exists(rel, trel.replace(os.sep, '/'), 'template')
        # CSS @import 依赖（样式级联，指向其它样式文件）
        for imp in ex['css_imports']:
            trel = os.path.normpath(os.path.join(os.path.dirname(rel), imp.lstrip('/')))
            add_edge_if_exists(rel, trel.replace(os.sep, '/'), 'cssimport')
        # HTML <link href> / <script src> 资源依赖（样式表与脚本）
        for a in ex['html_assets']:
            if a.startswith(('/', 'http://', 'https://', '//', '#', 'data:')):
                continue  # 绝对/外链不进项目图
            trel = os.path.normpath(os.path.join(os.path.dirname(rel), a))
            add_edge_if_exists(rel, trel.replace(os.sep, '/'), 'asset')
        for call in ex['calls']:
            # 跨文件调用边（仅当目标符号在别处定义）
            if call in symbols and symbols[call]['file'] != rel:
                key = (rel, symbols[call]['file'], 'calls')
                if key not in edge_keys:
                    edge_keys.add(key)
                    edges.append({'from': rel, 'to': symbols[call]['file'],
                                  'kind': 'calls', 'symbol': call})

    # 孤儿检测（规划 §5.6② 仅告警不裁决）：定义了但无人 extends/use/calls 引用的符号
    referenced = set()
    for ex in extracted.values():
        for c in ex['classes']:
            if c.get('extends'):
                referenced.add(c['extends'].lstrip('\\').split('\\')[-1].lower())
        for u in ex['uses']:
            referenced.add(u.split('\\')[-1].lower())
        for call in ex['calls']:
            referenced.add(call.lower())
    seen_orphan = set()
    for name, loc in symbols.items():
        short = name.split('\\')[-1].lower()
        if short not in referenced:
            key = (loc['file'], loc.get('line', 0), short)
            if key not in seen_orphan:
                seen_orphan.add(key)
                orphan_symbols.append({'name': name, 'file': loc['file'], 'line': loc.get('line', 0)})

    graph = {'nodes': nodes, 'edges': edges}
    meta = {
        'built_at': __import__('datetime').datetime.now().isoformat(),
        'tool_version': '1.0.0',
        'root': root,
        'file_hashes': {f: file_hash(os.path.join(root, f)) for f in file_list},
        'file_mtimes': {f: _safe_mtime(os.path.join(root, f)) for f in file_list},
        'lsp_available': lsp,
        'accuracy_report': {
            'edges_total': len(edges),
            'edges_valid': len([e for e in edges if os.path.exists(
                os.path.join(root, e['to']))]) if edges else 0,
            'edges_dangling': len(dangling),
            'symbols_total': len(symbols),
            'symbols_resolved': len(symbols),
            'symbols_orphan': len(orphan_symbols),
            'static_coverage': round(include_valid / include_total, 3) if include_total else 1.0,
            'include_total': include_total,
            'include_valid': include_valid,
            'lsp_available': lsp,
        },
        'dangling_edges': dangling,
        'orphan_symbols': orphan_symbols,
        'script_hash': file_hash(os.path.abspath(__file__)),
        # composer.json 哈希：autoload 映射改了 must 重建（extends/use 边依赖 PSR-4 映射）
        'composer_hash': file_hash(os.path.join(root, 'composer.json'))
            if os.path.isfile(os.path.join(root, 'composer.json')) else None,
    }
    # 原子写（规划 §5.5）
    _atomic_write(os.path.join(out_dir, 'graph.json'), graph)
    _atomic_write(os.path.join(out_dir, 'meta.json'), meta)
    _atomic_write(os.path.join(out_dir, 'symbols.json'), symbols)
    _write_markdown(os.path.join(out_dir, 'graph.md'), graph, root)
    print(f"[GRAPH-ACCURACY] 有效边 {meta['accuracy_report']['edges_valid']} / "
          f"悬空 {meta['accuracy_report']['edges_dangling']}（已剔除）/ "
          f"include解析率 {meta['accuracy_report']['static_coverage']} / LSP: "
          f"{','.join(k for k, v in lsp.items() if v) or 'none'}")
    _release_lock(root)
    return graph, meta, symbols


def _atomic_write(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _write_markdown(path, graph, root):
    """graph.md 人类兜底（agent 不加载，规划 §10）。"""
    lines = ['# 项目结构图谱（人类可读兜底，agent 不加载）', '']
    for rel, n in graph['nodes'].items():
        lines.append(f"- {rel}  [classes: {', '.join(n['classes']) or '-'}]")
    lines.append('')
    lines.append('## 边')
    for e in graph['edges']:
        lines.append(f"- {e['from']} --{e['kind']}--> {e['to']}")
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def query(graph, meta, symbols, root, q, direction='both', depth=2, all_cycles=False, max_nodes=80):
    """§9 查询接口 + 环检测，返回裁剪子图。

    all_cycles: False=仅检测 direction 可达闭包内的环（与「只警告已遍历子图」一致，
    down=依赖闭包/up=被依赖闭包互不越界）；True=对全图做有向 DFS 环检测，任意查询全局预警循环依赖
    （--direction down 也能报依赖间环）。默认行为不变，E2E-8 不破坏。
    """
    # 解析入口
    entry = None
    if q in graph['nodes']:
        entry = q
    elif q in symbols:
        entry = symbols[q]['file']
    else:
        # 尝试按文件名匹配
        for rel in graph['nodes']:
            if rel.endswith('/' + q) or rel == q:
                entry = rel
                break
    if not entry:
        print(f"[GRAPH-QUERY] 符号索引缺失：{q}（返回空子图，未做全图扫描）")
        return {'nodes': {}, 'edges': [], 'cycle': 0}

    # 构建邻接（按 direction）+ 平行边 kind 聚合（同 from→to 多种 kind 全保留），(from,to) 去重防重复遍历。
    adj = {'up': {}, 'down': {}}
    edge_kind_map = {}  # (from,to) -> 该有向边的全部 kind 列表（平行边聚合）
    seen_pair = set()
    for e in graph['edges']:
        key = (e['from'], e['to'])
        if key not in seen_pair:
            seen_pair.add(key)
            if e['to'] not in adj['down'].setdefault(e['from'], []):
                adj['down'][e['from']].append(e['to'])
            if e['from'] not in adj['up'].setdefault(e['to'], []):
                adj['up'][e['to']].append(e['from'])
        edge_kind_map.setdefault(key, [])
        if e['kind'] not in edge_kind_map[key]:
            edge_kind_map[key].append(e['kind'])

    MAX_NODES = max_nodes  # 节点预算硬上限（规划 §9 省 token：防枢纽模块 2 跳爆炸）
    visited = set()    # 全局去重：该节点已纳入子图（不论是否在当前递归路径）
    stack = set()      # 当前递归路径（仅用于真环判定的回边检测）
    subgraph_nodes = {}
    subgraph_edges = []
    cycles = [0]
    seen_cycle = set()  # 环边按 (from,to) 去重，仅保留一条（规划 §9「环只保留一条边」）
    # 环检测：在「有向(down)图」独立 DFS 回边计数，与查询方向解耦，保证守恒②③①：
    # ② 回边须沿 authored 方向(down)闭合，禁止 both/up 反向命中祖先的伪回边（菱形 DAG 假阳性）；
    # ① 自环 A→A 在有向 DFS 中只计 1 次（旧 both 模式 up/down 邻接各含 A 会计 2）。
    # 范围=direction 可达闭包（非仅 entry 的 down 集），否则 up/both 漏检 entry 纯上游环。
    def _reachable(entry, direction):
        dirs = []
        if direction in ('up', 'both'):
            dirs.append('up')
        if direction in ('down', 'both'):
            dirs.append('down')
        seen = {entry}
        stack = [entry]
        while stack:
            u = stack.pop()
            for dr in dirs:
                for v in adj[dr].get(u, []):
                    if v not in seen:
                        seen.add(v)
                        stack.append(v)
        return seen

    def detect_cycles(starts, allowed):
        vis = set(); st = set(); pairs = []
        def dfs(u):
            vis.add(u); st.add(u)
            for v in adj['down'].get(u, []):
                if v not in allowed:      # 不走出查询遍历范围，避免把范围外下游环算进来
                    continue
                if v in st:
                    pairs.append((u, v))   # u→v 沿 authored 方向闭合环
                elif v not in vis:
                    dfs(v)
            st.discard(u)
        for s in starts:
            if s not in vis:
                dfs(s)
        return pairs
    # 全局环检测模式：起点/范围=全图节点（不受 direction 闭包限制）；默认模式=遍历闭包
    if all_cycles:
        cyc_scope = set(graph['nodes'])
    else:
        cyc_scope = _reachable(entry, direction)
    cyc_pairs = detect_cycles(cyc_scope, cyc_scope)
    cyc_set = set(cyc_pairs)
    cycles[0] = len(cyc_pairs)

    def walk(node, d, came_from=None, came_dir=None):
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        if node in graph['nodes']:
            subgraph_nodes[node] = graph['nodes'][node]
        if d >= depth or len(subgraph_nodes) >= MAX_NODES:
            stack.discard(node)
            return
        dirs = []
        if direction in ('up', 'both'):
            dirs.append('up')
        if direction in ('down', 'both'):
            dirs.append('down')
        for dr in dirs:
            for nxt in adj[dr].get(node, []):
                if len(subgraph_nodes) >= MAX_NODES:
                    return
                # both 模式"刚走过的同一条边的逆向遍历"是伪环（A→B 再 up 回 A）；
                # 仅 nxt==came_from 且 dr!=came_dir 才跳过。真 2 节点互环两向相同(dr==came_dir)，不算伪环。
                if nxt == came_from and dr != came_dir:
                    continue
                # 仅「有向图 DFS 真回边」(node,nxt)∈cyc_set 且在当前路径上才算环；
                # 菱形/重复边目标节点虽 visited 但非 stack 上的 down 回边→不计。
                if nxt in stack and dr == 'down' and (node, nxt) in cyc_set:
                    # 环边引用的祖先节点可能不在子图节点集，补入避免人类兜底 graph.md 引用缺失（B-2）
                    if nxt in graph['nodes']:
                        subgraph_nodes.setdefault(nxt, graph['nodes'][nxt])
                    if (node, nxt) not in seen_cycle:
                        seen_cycle.add((node, nxt))
                        subgraph_edges.append({'from': node, 'to': nxt,
                                               'kind': 'cycle'})
                    continue
                # 平行边：取 (node,nxt) 或 (nxt,node) 的全部 kind，逐条产出（不覆盖）
                kinds = edge_kind_map.get((node, nxt)) or edge_kind_map.get(
                    (nxt, node)) or ['include']
                for k in kinds:
                    subgraph_edges.append({'from': node, 'to': nxt, 'kind': k})
                walk(nxt, d + 1, came_from=node, came_dir=dr)
        stack.discard(node)

    walk(entry, 0)
    if cycles[0]:
        print(f"[GRAPH-CYCLE] 检测到 {cycles[0]} 个环（已在子图中折叠）")
    return {'nodes': subgraph_nodes, 'edges': subgraph_edges, 'cycle': cycles[0]}


def _graph_files_present(root):
    """B1：图谱三件套（graph/meta/symbols）是否齐全。任一缺失 → query 入口须重建，避免 open 崩溃。"""
    kg = os.path.join(root, '.ai-memory', 'knowledge-graph')
    return all(os.path.isfile(os.path.join(kg, f))
               for f in ('graph.json', 'meta.json', 'symbols.json'))


def need_rebuild(root):
    """规划 §6 新鲜度：比对 mtime+内容哈希。

    返回 (stale, changed_files)：
    - changed_files: set of changed file rels（增量提示），None 表示需全量重建
      （脚本升级/composer.json 变更/文件删除/产物缺失等无法增量的情况）。
    注意：即便返回 changed_files，build 仍全量 extract——因 CONST_TABLE 全局依赖
    （改 A.php 的 define 会影响 B.php 的 include 解析），extract 增量风险过高，留作 v2。
    """
    meta_path = os.path.join(root, '.ai-memory', 'knowledge-graph', 'meta.json')
    if not os.path.exists(meta_path):
        return True, None
    try:
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
    except Exception:
        return True, None
    changed_files = set()
    current_rels = set()  # B3：记录现存源文件，检测"删除"
    mtimes = meta.get('file_mtimes', {})  # 廉价 mtime 前置过滤：mtime 未变则内容必未变
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS
                       and not d.startswith('.')]
        for fn in filenames:
            if fn.endswith(SRC_EXTS):
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, root).replace(os.sep, '/')
                current_rels.add(rel)
                # mtime 一致（旧版无 file_mtimes 时 mtimes={} → 回退全量 md5）
                if rel in mtimes and mtimes[rel] == _safe_mtime(p):
                    continue
                h = file_hash(p)
                if rel not in meta.get('file_hashes', {}) or meta['file_hashes'][rel] != h:
                    changed_files.add(rel)
    # B3：meta 记录的文件已不在当前树（被删）→ 无法增量，返回 None
    if set(meta.get('file_hashes', {})) - current_rels:
        return True, None
    # 脚本版本/composer.json 变化：无法增量，返回 None
    if meta.get('script_hash') != file_hash(os.path.abspath(__file__)):
        return True, None
    cj = os.path.join(root, 'composer.json')
    if os.path.isfile(cj):
        if file_hash(cj) != meta.get('composer_hash'):
            return True, None
    elif meta.get('composer_hash') is not None:
        return True, None
    return len(changed_files) > 0, changed_files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=os.getcwd())
    ap.add_argument('--query', help='入口 file 或 symbol，多个逗号分隔合并子图')
    ap.add_argument('--direction', default='both', choices=['up', 'down', 'both'])
    ap.add_argument('--depth', type=int, default=2)
    ap.add_argument('--rebuild', action='store_true', help='强制全量重建')
    ap.add_argument('--no-rebuild', action='store_true',
                    help='跳过新鲜度检测，直接复用已缓存图谱（仅在确认图谱新鲜的连续查询时使用）')
    ap.add_argument('--all-cycles', action='store_true',
                    help='全局环检测：对任意查询都全图 DFS 预警循环依赖（不受 --direction 闭包限制），默认关')
    ap.add_argument('--exclude', default=None,
                    help='追加排除目录（逗号分隔），合并到默认排除 + .graphignore')
    ap.add_argument('--max-nodes', type=int, default=80,
                    help='查询子图节点预算硬上限（默认 80，防枢纽模块爆炸）')
    ap.add_argument('--selftest', action='store_true',
                    help='运行内置 E2E 自检（删文件无悬挂边 + 改文件过期判定），不改交付物')
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    # 初始化运行时排除集（合并默认 + .graphignore + --exclude）
    _EXCLUDE_DIRS.clear()
    _EXCLUDE_DIRS.update(load_exclude_dirs(root, args.exclude))
    if args.selftest:
        import tempfile as _tf
        import shutil as _shutil
        # B-3：在副本运行，避免触碰用户原始交付物（旧版会 rename/改写原文件）
        work = _tf.mkdtemp(prefix='kg_selftest_')
        _shutil.copytree(root, work, dirs_exist_ok=True,
                         ignore=_shutil.ignore_patterns('.ai-memory', '.codebuddy', '.git'))
        kg = os.path.join(work, '.ai-memory', 'knowledge-graph')
        def load():
            return (json.load(open(os.path.join(kg, 'graph.json'), encoding='utf-8')),
                    json.load(open(os.path.join(kg, 'meta.json'), encoding='utf-8')),
                    json.load(open(os.path.join(kg, 'symbols.json'), encoding='utf-8')))
        build(work)
        g, m, s = load()
        # E2E-5: 注释伪符号回归（build_graph 注释缺陷防护，ERR-006）。
        # 构造最小 PHP fixture：真实符号 + 注释/死代码中的伪符号，build 后断言
        # symbols.json 不含伪符号、edges 不含指向伪符号的假 extends/calls 边。
        # 须置于 victim 早返回（非 include 项目会早退）之前，确保任何项目均跑此断言。
        fx_dir = os.path.join(work, '__kg_phantom_fixture__')
        os.makedirs(fx_dir, exist_ok=True)
        fx = os.path.join(fx_dir, 'phantom.php')
        with open(fx, 'w', encoding='utf-8') as _f:
            _f.write(
                "<?php\n"
                "// class KgTestPhantomCls extends RealClass\n"   # 行注释伪类
                "// KgTestPhantomHelper::go();\n"                 # 行注释伪静态调用
                "/* class KgTestPhantomDead {} */\n"              # 块注释伪类
                "class RealClass {}\n"                        # 真实类
                "function realFunc() {}\n"                    # 真实函数
                "$o = new RealClass();\n"                     # 真实实例化
                "RealClass::const();\n"                       # 真实静态调用
            )
        build(work)
        g5, _, s5 = load()
        phantom_names = ('KgTestPhantomCls', 'KgTestPhantomDead', 'KgTestPhantomHelper')
        # 仅断言 fixture 文件自身的 symbols：build() 会扫描 build_graph.py 自身，
        # 其源码内嵌的 fixture 字符串字面量里 `class Xxx` 会被 RE_CLASS 误抽，
        # 故须按文件归属过滤，避免自扫描导致的假阳性（非代码缺陷）。
        fx_rel = '__kg_phantom_fixture__/phantom.php'
        fx_syms = [n for n, loc in s5.items()
                   if isinstance(loc, dict) and loc.get('file') == fx_rel]
        phantom_syms = [n for n in phantom_names if n in fx_syms]
        print('[E2E-5] 伪符号命中:', phantom_syms, '(期望 [])')
        assert not phantom_syms, '[E2E-5] 注释伪符号未过滤: %s' % phantom_syms
        # 真实符号须保留（避免 strip 误伤正常代码）。须断言 fixture 文件自身 fx_syms 而非全局 s5：
        # build() 会扫描自身（.py），其内嵌 fixture 字符串里的 `class RealClass` 曾被 RE_CLASS 误抽进 s5 兜底，
        # 用全局 s5 会使本断言"假通过"——即使 fixture 真实符号被误剥，s5 仍有同名符号。
        assert 'RealClass' in fx_syms, '[E2E-5] fixture 真实符号 RealClass 被误剥（fx_syms 缺失）'
        # edges 不得含指向伪符号的 symbol（extends/calls/autoload 均经 symbols 命中，伪符号不在表中则无假边）
        phantom_edges = [e for e in g5['edges']
                         if e.get('symbol') in phantom_names]
        print('[E2E-5] 指向伪符号的假边:', len(phantom_edges), '(期望 0)')
        assert not phantom_edges, '[E2E-5] 存在指向注释伪符号的假边'
        print('[E2E-5] 通过：注释伪符号已过滤，真实符号保留')
        # E2E-6: strip_php_comments 须保留换行（ERR-006 同族），否则真实符号行号上移、改动定位失真。
        _s6_in = (
            "<?php\n"
            "class A {}\n"        # line 2
            "/* multi\n"          # line 3
            "   line comment\n"    # line 4
            "*/\n"                # line 5
            "class B {}\n"        # line 6（strip 后仍须在第 6 行）
        )
        _s6_out = strip_php_comments(_s6_in)
        _s6_nl_in = _s6_in.count('\n')
        _s6_nl_out = _s6_out.count('\n')
        print('[E2E-6] 换行数 输入/输出:', _s6_nl_in, '/', _s6_nl_out, '(期望相等)')
        assert _s6_nl_out == _s6_nl_in, \
            '[E2E-6] 块注释删除内部换行致行号位移：去 %d 行' % (_s6_nl_in - _s6_nl_out)
        assert 'class B' in _s6_out, '[E2E-6] 真实符号 B 被块注释误吞'
        print('[E2E-6] 通过：块注释内部换行已保留，行号不位移')
        # E2E-7: 符号抽取语言隔离（issue-2）。非 PHP 文件不得被 PHP 正则误抽；PHP 文件仍须正常抽取。
        _py_f = os.path.join(work, '__kg_lang_iso__.py')
        with open(_py_f, 'w', encoding='utf-8') as _f:
            _f.write("class FakeCls:\n    x = new RealCls()\n")
        _js_f = os.path.join(work, '__kg_lang_iso__.js')
        with open(_js_f, 'w', encoding='utf-8') as _f:
            _f.write("class KgTestPhantomCls { go() { this.helper() } }\n")
        _php_f = os.path.join(work, '__kg_lang_iso__.php')
        with open(_php_f, 'w', encoding='utf-8') as _f:
            _f.write("<?php\nclass RealPhpCls {}\n")
        _ex_py = extract_file(_py_f, work)
        _ex_js = extract_file(_js_f, work)
        _ex_php = extract_file(_php_f, work)
        _py_classes = [c['name'] for c in _ex_py['classes']]
        _js_classes = [c['name'] for c in _ex_js['classes']]
        print('[E2E-7] .py 误抽 class:', _py_classes, '(期望 [])')
        print('[E2E-7] .js 误抽 class:', _js_classes, '(期望 [])')
        assert not _py_classes, '[E2E-7] .py 被误抽 PHP 符号: %s' % _py_classes
        assert not _js_classes, '[E2E-7] .js 被误抽 PHP 符号: %s' % _js_classes
        # PHP 抽取未被连带禁用（回归：非 PHP 门禁不能误伤 PHP）
        _php_classes = [c['name'] for c in _ex_php['classes']]
        assert 'RealPhpCls' in _php_classes, \
            '[E2E-7] PHP 真实类未被抽取（门禁误伤）: %s' % _php_classes
        print('[E2E-7] 通过：非 PHP 零误抽，PHP 抽取保留')
        # E2E-8: 环检测三守恒回归（历史犯错最多，karpathy 守恒 + ERR-004）：
        # ① 计数不重不漏 ② 遍历方向与边有向性一致 ③ 平行边不翻倍。
        # 直接构造图 dict 调 query()（免建文件），覆盖 7 例（菱形DAG/3环/互环2/自环/平行边/3环(up)/上游环(up)）。
        def _mk_g(nodes, edges):
            return {'nodes': {n: {} for n in nodes},
                    'edges': [{'from': a, 'to': b, 'kind': 'include'} for a, b in edges]}
        _cyc_cases = [
            # (name, nodes, edges, direction, expect_cycle)  — 期望见 karpathy 守恒
            ('菱形DAG(both)', ['A', 'B', 'C', 'D'],
             [('A', 'B'), ('A', 'C'), ('B', 'D'), ('C', 'D')], 'both', 0),   # 守恒②：反向遍历命中祖先不得算环
            ('真实3环(both)', ['A', 'B', 'C'],
             [('A', 'B'), ('B', 'C'), ('C', 'A')], 'both', 1),                # 守恒①②
            ('互环2(both)', ['A', 'B'],
             [('A', 'B'), ('B', 'A')], 'both', 1),                            # 守恒①②
            ('自环(both)', ['A'], [('A', 'A')], 'both', 1),                   # 守恒①：旧实现计 2，须 1
            ('平行边(both)', ['A', 'B'],
             [('A', 'B'), ('A', 'B')], 'both', 0),                            # 守恒③：平行边不翻倍
            ('真实3环(up)', ['A', 'B', 'C'],
             [('A', 'B'), ('B', 'C'), ('C', 'A')], 'up', 1),                  # 守恒②：up 模式仍须检出真环
            ('上游环(up)', ['X', 'Y', 'Z'],
             [('Y', 'X'), ('Y', 'Z'), ('Z', 'Y')], 'up', 1),                  # 守恒②：entry 纯上游 Y↔Z 环须检出（entry 不在环上）
        ]
        for _cn, _nd, _ed, _dir, _exp in _cyc_cases:
            _gr = _mk_g(_nd, _ed)
            _r = query(_gr, {}, {}, work, _nd[0], direction=_dir, depth=5)
            print('[E2E-8] %s 环数: %s (期望 %s)' % (_cn, _r['cycle'], _exp))
            assert _r['cycle'] == _exp, \
                '[E2E-8] %s 环数=%s 期望 %s（守恒违反）' % (_cn, _r['cycle'], _exp)
        print('[E2E-8] 通过：环检测三守恒（不重不漏/方向一致/平行边不翻倍）均满足')
        # E2E-9: 全局环检测开关（改进项1）。图 A↔B 成环、A→X（X 下游汇点）；
        # entry=X --direction down 默认只遍历闭包 {X} → 0 环；--all-cycles 全图 DFS → 命中 A↔B → 1 环。
        _g9 = _mk_g(['A', 'B', 'X'], [('A', 'B'), ('B', 'A'), ('A', 'X')])
        _r9_def = query(_g9, {}, {}, work, 'X', direction='down', depth=5, all_cycles=False)
        print('[E2E-9] 默认(down,entry=X) 环数: %s (期望 0)' % _r9_def['cycle'])
        assert _r9_def['cycle'] == 0, '[E2E-9] 默认模式误报闭包外环: %s' % _r9_def['cycle']
        _r9_all = query(_g9, {}, {}, work, 'X', direction='down', depth=5, all_cycles=True)
        print('[E2E-9] 全局(--all-cycles,down,entry=X) 环数: %s (期望 1)' % _r9_all['cycle'])
        assert _r9_all['cycle'] == 1, '[E2E-9] 全局模式漏报全图环: %s' % _r9_all['cycle']
        print('[E2E-9] 通过：全局环检测开关生效且不破坏默认闭包行为')
        # E2E-3: 选一个被依赖的真实源文件，删之，重建后其依赖边应不残留（悬空已剔除）
        victim = None
        for e in g['edges']:
            if e['kind'] == 'include' and os.path.exists(os.path.join(work, e['to'])):
                victim = e['to']
                break
        if not victim:
            # 非 PHP/JS include 项目（纯 import/use、空图谱等）无可用 victim，
            # 优雅跳过并清理临时副本，避免 AssertionError 崩溃 + 残留目录。
            _shutil.rmtree(work)
            print('[SELFTEST] 跳过 E2E-3/4：当前目录图谱无 include 边（非 PHP/JS include 项目），无法构造 victim（副本已清理）')
            return
        dependents = [e['from'] for e in g['edges'] if e['to'] == victim]
        print('[E2E-3] 依赖', victim, '的文件数:', len(dependents))
        bak = os.path.join(work, victim) + '.baktest'
        os.rename(os.path.join(work, victim), bak)
        build(work)
        g2, _, _ = load()
        hanging = [e for e in g2['edges'] if e['to'] == victim]
        print('[E2E-3] 删除后悬挂边:', len(hanging), '(期望 0)')
        os.rename(bak, os.path.join(work, victim))
        # E2E-4: 改一个真实文件，need_rebuild 应报 stale
        orig = open(os.path.join(work, victim), encoding='utf-8', errors='ignore').read()
        open(os.path.join(work, victim), 'a', encoding='utf-8').write('\n// e2e touch\n')
        stale, changed_info = need_rebuild(work)
        cnt = len(changed_info) if changed_info else '全量'
        print('[E2E-4] 编辑后过期:', stale, '变更文件数:', cnt, '(期望 True/>0)')
        open(os.path.join(work, victim), 'w', encoding='utf-8').write(orig)
        _shutil.rmtree(work)
        print('[SELFTEST] 完成（副本已清理，原交付物未改动）')
        return
    kg_dir = os.path.join(root, '.ai-memory', 'knowledge-graph')

    # 冷启动 / 新鲜度（规划 §6）
    if args.rebuild:
        build(root)
        return
    if args.query:
        if args.no_rebuild and _graph_files_present(root):
            print('[GRAPH-USED-CACHE] 跳过新鲜度检测，复用已缓存图谱')
        else:
            stale, changed_info = need_rebuild(root)
            # B1：meta.json 在但 graph.json/symbols.json 缺失（被误删/损坏）→ 即便源码未变也必须重建，
            # 否则下方直接 open(graph.json) 会抛 FileNotFoundError 崩溃。
            if stale or not _graph_files_present(root):
                if changed_info:
                    preview = ', '.join(sorted(changed_info)[:5])
                    suffix = '…' if len(changed_info) > 5 else ''
                    print(f"[GRAPH-STALE] {len(changed_info)} 个文件变更：{preview}{suffix}，正在重建…")
                else:
                    print("[GRAPH-STALE] 图谱过期（产物缺失/脚本升级/composer.json 变更），正在全量重建…")
                build(root)  # 全量重抽保准确性（extract 增量因 CONST_TABLE 依赖风险留作 v2）
            else:
                print("[GRAPH-FRESH] 图谱新鲜")
        with open(os.path.join(kg_dir, 'graph.json'), encoding='utf-8') as f:
            graph = json.load(f)
        with open(os.path.join(kg_dir, 'meta.json'), encoding='utf-8') as f:
            meta = json.load(f)
        with open(os.path.join(kg_dir, 'symbols.json'), encoding='utf-8') as f:
            symbols = json.load(f)
        # P1：支持多入口（逗号分隔），合并子图——覆盖 SKILL.md Step2 P1「--query <改动文件1,改动文件2,…>」
        # 查依赖闭包的使用方式；单入口时退化为原行为。
        merged = {'nodes': {}, 'edges': [], 'cycle': 0}
        for q in args.query.split(','):
            q = q.strip()
            if not q:
                continue
            sub = query(graph, meta, symbols, root, q, args.direction, args.depth,
                        args.all_cycles, args.max_nodes)
            merged['nodes'].update(sub['nodes'])
            merged['edges'].extend(sub['edges'])
            merged['cycle'] += sub['cycle']
        print(json.dumps(merged, ensure_ascii=False))
        return
    # 默认：全量构建
    build(root)


if __name__ == '__main__':
    main()
