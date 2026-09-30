#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse hook (GLOBAL): SQL 注入风险检查。

检测修改文件中的 SQL 注入风险模式，覆盖 PHP / Python / JS / Java / Go：

风险模式（命中即警告）：
  1. PHP 用户输入直接入 SQL：$_GET/$_POST/$_REQUEST/$_COOKIE 出现在 SQL 字符串中
  2. PHP 字符串拼接 SQL："SELECT ..." . $var
  3. PHP 变量插值 SQL（双引号）："SELECT ... $var" / "SELECT ... {$var}"
  4. Python f-string SQL：f"SELECT ... {var}"
  5. Python % 格式化 SQL："SELECT ... %s" % var（仅当含用户输入标记时）
  6. JS 模板字符串 SQL：`SELECT ... ${var}`
  7. Java 字符串拼接 SQL："SELECT ..." + var

SQL 关键字覆盖：
  - SQL 标准：SELECT / INSERT INTO / UPDATE / DELETE FROM / DROP TABLE /
    ALTER TABLE / CREATE TABLE / UNION SELECT / TRUNCATE TABLE
  - MySQL/MariaDB 特有：REPLACE INTO / LOAD DATA INFILE / LOAD DATA LOCAL INFILE /
    INTO OUTFILE / INTO DUMPFILE / GRANT / REVOKE / CALL

安全模式（同行出现则跳过，不误报）：
  - 预处理语句：prepare( / prepare "
  - 参数绑定：bindParam / bindValue / bind_param
  - ORM 查询构造器：->where( / ->table( / ::table( / .where(
  - 批量执行：executemany

非阻断 exit 1 回显 AI（与 select_star.py 一致）。
"""
import sys
import os
import json
import re

# 受检查的文件扩展名
TEXT_EXT = {".php", ".phtml", ".php3", ".php5", ".py", ".js", ".jsx",
            ".ts", ".tsx", ".java", ".go", ".rb", ".sql", ".inc"}

# SQL 关键字前缀（匹配 SQL 语句开头）
# 覆盖 SQL 标准 + MySQL/MariaDB/PostgreSQL 特有高危语法
SQL_KEYWORDS = (
    r"(?:SELECT\s|INSERT\s+INTO|UPDATE\s|DELETE\s+FROM|DROP\s+TABLE|"
    r"ALTER\s+TABLE|CREATE\s+TABLE|UNION\s+SELECT|TRUNCATE\s+TABLE|"
    r"REPLACE\s+INTO|"
    r"LOAD\s+DATA\s+INFILE|LOAD\s+DATA\s+LOCAL\s+INFILE|"  # MySQL/MariaDB 读文件
    r"INTO\s+OUTFILE|INTO\s+DUMPFILE|"                      # MySQL/MariaDB 写文件
    r"GRANT\s|REVOKE\s|"                                    # 权限操纵
    r"CALL\s)"                                              # 存储过程调用
)

# 风险模式：(正则, 描述)
RISK_PATTERNS = [
    # PHP: $_GET/$_POST/$_REQUEST/$_COOKIE 直接出现在 SQL 字符串中
    (re.compile(
        r'["\'][^"\']*' + SQL_KEYWORDS + r'[^"\']*\$_(?:GET|POST|REQUEST|COOKIE|SERVER)\s*\[',
        re.IGNORECASE),
     "PHP 用户输入直接入 SQL（$_GET/$_POST/$_REQUEST）"),

    # PHP: 字符串拼接 SQL "SELECT ..." . $var 或 "SELECT ..." . $obj->prop
    (re.compile(
        r'["\']\s*' + SQL_KEYWORDS + r'.*?["\']\s*\.\s*\$',
        re.IGNORECASE),
     "PHP 字符串拼接 SQL"),

    # PHP: 双引号变量插值 SQL "SELECT ... $var" 或 "SELECT ... {$var}"
    (re.compile(
        r'"[^"]*' + SQL_KEYWORDS + r'[^"]*\$(?:[a-zA-Z_]|\{)',
        re.IGNORECASE),
     "PHP 变量插值 SQL（双引号内 $var）"),

    # Python: f-string SQL f"SELECT ... {var}" 或 f'SELECT ... {var}'
    (re.compile(
        r'f["\']\s*' + SQL_KEYWORDS + r'[^"\']*\{',
        re.IGNORECASE),
     "Python f-string SQL（变量插值）"),

    # Python: % 格式化 SQL "SELECT ... %s" % var（仅当 var 是用户输入相关时）
    (re.compile(
        r'["\']\s*' + SQL_KEYWORDS + r'[^"\']*%s[^"\']*["\']\s*%\s*\(',
        re.IGNORECASE),
     "Python % 格式化 SQL（疑似拼接）"),

    # JS: 模板字符串 SQL `SELECT ... ${var}`
    (re.compile(
        r'`\s*' + SQL_KEYWORDS + r'[^`]*\$\{',
        re.IGNORECASE),
     "JS 模板字符串 SQL（变量插值）"),

    # Java: 字符串拼接 SQL "SELECT ..." + var
    (re.compile(
        r'"\s*' + SQL_KEYWORDS + r'[^"]*"\s*\+\s*\w',
        re.IGNORECASE),
     "Java 字符串拼接 SQL"),
]

# 安全模式（同行出现则跳过）
SAFE_PATTERNS = [
    re.compile(r'\bprepare\s*\(', re.IGNORECASE),      # PDO/MySQLi prepare
    re.compile(r'\bprepare\s+"', re.IGNORECASE),        # Python DB-API prepare
    re.compile(r'\bbindParam\b', re.IGNORECASE),        # PDO bindParam
    re.compile(r'\bbindValue\b', re.IGNORECASE),        # PDO bindValue
    re.compile(r'\bbind_param\b', re.IGNORECASE),       # MySQLi bind_param
    re.compile(r'->where\s*\(', re.IGNORECASE),         # ORM where
    re.compile(r'->table\s*\(', re.IGNORECASE),         # ORM table
    re.compile(r'::table\s*\(', re.IGNORECASE),         # ORM static table
    re.compile(r'\.where\s*\(', re.IGNORECASE),         # JS ORM where
    re.compile(r'\bexecutemany\b', re.IGNORECASE),      # Python executemany
]

# 跳过注释行的逻辑（与 select_star.py 一致）
def _is_comment(s):
    return (s.startswith("//") or s.startswith("#") or
            s.startswith("*") or s.startswith("/*"))


def find_sql_injection_risks(text):
    """逐行扫描，跳过注释，返回 (行号, 描述, 行内容) 列表。

    对每行：
    1. 跳过注释行
    2. 检查是否含风险模式
    3. 若命中风险模式，检查同行是否有安全模式（有则跳过）
    """
    hits = []
    in_block = False
    for i, line in enumerate(text.splitlines(), start=1):
        s = line.strip()

        # 块注释处理
        if in_block:
            if "*/" in line:
                in_block = False
            continue
        if "/*" in line:
            if "*/" in line:
                continue
            in_block = True
            continue

        # 单行注释跳过
        if _is_comment(s):
            continue

        # 检查风险模式
        for pattern, desc in RISK_PATTERNS:
            if pattern.search(line):
                # 检查同行是否有安全模式
                is_safe = any(sp.search(line) for sp in SAFE_PATTERNS)
                if not is_safe:
                    hits.append((i, desc, s[:100]))
                    break  # 同行只报一次
    return hits


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        data = json.loads(raw)
    except Exception:
        return 0

    tool_input = data.get("tool_input", {}) or {}
    path = (
        tool_input.get("filePath")
        or tool_input.get("file_path")
        or tool_input.get("path")
        or ""
    )
    if not path:
        return 0
    path = os.path.abspath(path)
    if os.path.splitext(path)[1].lower() not in TEXT_EXT:
        return 0
    if not os.path.isfile(path):
        return 0

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return 0

    hits = find_sql_injection_risks(text)
    if hits:
        print("[SQL-INJECTION-WARN] 发现 SQL 注入风险（字符串拼接/变量插值）：")
        for line_no, desc, preview in hits:
            print("  行 %d [%s] %s" % (line_no, desc, preview))
        print("建议改用预处理语句（prepare + bindParam/bindValue）或 ORM 查询构造器。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
