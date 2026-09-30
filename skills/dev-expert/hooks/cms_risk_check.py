#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse hook: 国内常用 CMS（帝国/织梦/Discuz/WordPress/PHPCMS）高危风险检测。

检测 5 类风险：
1. 文件包含漏洞：include/require + $_GET/$_POST/$_REQUEST/$_COOKIE
2. 命令执行：eval/system/exec/passthru/shell_exec/popen/proc_open/assert + 用户输入
3. 反射型 XSS：echo/print/printf + $_GET/$_POST/$_REQUEST 未转义
4. 任意文件上传：move_uploaded_file 目标路径不可控
5. SSRF/远程包含：include/require + http:// 或 https://

安全模式（不报警）：
- htmlspecialchars/htmlentities/esc_html/esc_url/e() 转义函数
- intval/floatval 强制类型转换
- 常量/配置变量（如 DIR_FS_*, __DIR__）
"""
import sys
import os
import json
import re

# 仅检查 PHP 文件（国内 CMS 主要语言）
TARGET_EXT = ".php"

# 用户输入源（PHP 超全局变量）
USER_INPUT = r"\$_(?:GET|POST|REQUEST|COOKIE|SERVER)\b"

# 转义/安全函数（同行出现则跳过）
SAFE_FUNC = (
    r"htmlspecialchars", r"htmlentities", r"strip_tags",
    r"esc_html", r"esc_attr", r"esc_url", r"esc_js",
    r"intval", r"floatval", r"doubleval",
    r"\be\(",  # Laravel Blade 的 e() 转义
    r"wp_kses", r"sanitize_text_field",
    r"addslashes",
)

# 风险模式
PATTERNS = [
    # 1. 文件包含漏洞
    {
        "id": "FILE_INCLUDE",
        "regex": re.compile(
            r"(?:include|require|include_once|require_once)\s*\(?\s*"
            r"(?:\$_(?:GET|POST|REQUEST|COOKIE)\b"
            r"|\$[a-z_]\w*\s*\.\s*\$_(?:GET|POST|REQUEST|COOKIE)\b)",
            re.IGNORECASE
        ),
        "msg": "文件包含漏洞：include/require 直接使用用户输入，可能导致 LFI/RFI",
    },
    # 2. 远程文件包含（SSRF）
    {
        "id": "RFI_SSRF",
        "regex": re.compile(
            r"(?:include|require|include_once|require_once)\s*\(?\s*"
            r"['\"]https?://",
            re.IGNORECASE
        ),
        "msg": "远程文件包含/SSRF：include/require 远程 URL，极高风险",
    },
    # 3. 命令执行：eval/assert + 用户输入
    {
        "id": "CODE_EXEC",
        "regex": re.compile(
            r"(?:eval|assert)\s*\(\s*"
            r"(?:\$_(?:GET|POST|REQUEST|COOKIE)\b"
            r"|base64_decode\s*\(\s*\$_)",
            re.IGNORECASE
        ),
        "msg": "代码执行漏洞：eval/assert 执行用户输入，极高风险（常见后门）",
    },
    # 4. 命令执行：system/exec/passthru/shell_exec/popen/proc_open + 用户输入
    {
        "id": "CMD_EXEC",
        "regex": re.compile(
            r"(?:system|exec|passthru|shell_exec|popen|proc_open)\s*\(\s*"
            r"(?:\$_(?:GET|POST|REQUEST|COOKIE)\b"
            r"|\$[a-z_]\w*\s*\(\s*\$_(?:GET|POST|REQUEST|COOKIE)\b)",
            re.IGNORECASE
        ),
        "msg": "命令执行漏洞：system/exec/passthru 执行用户输入",
    },
    # 5. 反射型 XSS：echo/print + $_GET/$_POST 未转义
    {
        "id": "XSS_REFLECT",
        "regex": re.compile(
            r"(?:echo|print|printf)\b[^;]{0,80}"
            r"\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "反射型 XSS：直接输出用户输入未转义",
    },
    # 6. 任意文件上传：move_uploaded_file + 可控路径
    {
        "id": "FILE_UPLOAD",
        "regex": re.compile(
            r"move_uploaded_file\s*\([^,]+,\s*"
            r"(?:\$_(?:GET|POST|REQUEST)\b"
            r"|\$[a-z_]\w*\s*\.\s*\$_(?:GET|POST|REQUEST)\b)",
            re.IGNORECASE
        ),
        "msg": "任意文件上传：move_uploaded_file 目标路径含用户输入",
    },
    # 7. SQL 拼接 + 帝国CMS 特有 $empire->query 拼接
    {
        "id": "CMS_SQL_QUERY",
        "regex": re.compile(
            r"(?:empire->query|empire->fetch|db->query|db->fetchAll)\s*\(\s*"
            r"[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "CMS SQL 注入：帝国/织梦 DB 对象拼接用户输入",
    },
    # 8. 织梦 DedeCMS 特有：$dsql->ExecuteNoneQuery 拼接
    {
        "id": "DEDESQL",
        "regex": re.compile(
            r"dsql->(?:ExecuteNoneQuery|Execute|GetOne)\s*\(\s*"
            r"[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "织梦 DedeCMS SQL 注入：$dsql 拼接用户输入",
    },
    # 9. Discuz! 特有：DB::query 拼接
    {
        "id": "DISCUZSQL",
        "regex": re.compile(
            r"DB::query\s*\(\s*[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "Discuz! SQL 注入：DB::query 拼接用户输入",
    },
    # 10. WordPress 特有：$wpdb->query 拼接
    {
        "id": "WPSQL",
        "regex": re.compile(
            r"wpdb->(?:query|get_results|get_var|get_row|get_col)\s*\(\s*"
            r"[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "WordPress SQL 注入：$wpdb->query/get_results 拼接用户输入",
    },
    # 11. PHPCMS 特有：$this->db->query / pc_base::load_model 拼接
    {
        "id": "PHPCMS_SQL",
        "regex": re.compile(
            r"(?:this->db->query|this->db->select|this->db->get_one)\s*\(\s*"
            r"[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "PHPCMS SQL 注入：$this->db->query/select 拼接用户输入",
    },
    # 12. Drupal 特有：db_query / db_select 拼接
    {
        "id": "DRUPAL_SQL",
        "regex": re.compile(
            r"(?:db_query|db_select|db_delete|db_update|db_insert|db_merge)\s*\(\s*"
            r"[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "Drupal SQL 注入：db_query/db_select 拼接用户输入",
    },
    # 13. Joomla 特有：$db->setQuery / $db->loadResult 拼接
    {
        "id": "JOOMLA_SQL",
        "regex": re.compile(
            r"db->(?:setQuery|loadResult|loadObjectList|loadAssocList|loadRow)\s*\(\s*"
            r"[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "Joomla SQL 注入：$db->setQuery/loadResult 拼接用户输入",
    },
    # 14. ThinkPHP 特有：Db::query / M()->query / $model->query 拼接
    {
        "id": "THINKPHP_SQL",
        "regex": re.compile(
            r"(?:Db::query|Db::execute|M\(\w+\)->query|model->query|model->execute)\s*\(\s*"
            r"[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "ThinkPHP SQL 注入：Db::query/M()->query 拼接用户输入",
    },
    # 15. CodeIgniter 特有：$this->db->query 拼接
    {
        "id": "CI_SQL",
        "regex": re.compile(
            r"this->db->query\s*\(\s*[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "CodeIgniter SQL 注入：$this->db->query 拼接用户输入",
    },
    # 16. Laravel 特有：DB::select / DB::statement 拼接（非预处理方式）
    {
        "id": "LARAVEL_SQL",
        "regex": re.compile(
            r"DB::(?:select|statement|unprepared)\s*\(\s*[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "Laravel SQL 注入：DB::select/statement/unprepared 拼接用户输入",
    },
    # 17. Yii 特有：Yii::$app->db->createCommand 拼接
    {
        "id": "YII_SQL",
        "regex": re.compile(
            r"db->createCommand\s*\(\s*[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "Yii SQL 注入：createCommand 拼接用户输入",
    },
    # 18. Symfony 特有：$conn->executeQuery 拼接
    {
        "id": "SYMFONY_SQL",
        "regex": re.compile(
            r"conn->(?:executeQuery|executeUpdate|executeStatement)\s*\(\s*"
            r"[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "Symfony SQL 注入：executeQuery 拼接用户输入",
    },
    # 19. Typecho 特有：$db->query / $db->fetchRow 拼接
    {
        "id": "TYPECHO_SQL",
        "regex": re.compile(
            r"db->(?:query|fetchRow|fetchALL)\s*\(\s*[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "Typecho SQL 注入：$db->query/fetchRow 拼接用户输入",
    },
    # 20. Z-Blog 特有：$zbp->db->query 拼接
    {
        "id": "ZBLOG_SQL",
        "regex": re.compile(
            r"zbp->db->query\s*\(\s*[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "Z-Blog SQL 注入：$zbp->db->query 拼接用户输入",
    },
    # 21. emlog 特有：$db->query / $db->fetch_array 拼接
    {
        "id": "EMLOG_SQL",
        "regex": re.compile(
            r"\bdb->(?:query|fetch_array|fetch_row|num_rows)\s*\(\s*"
            r"[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "emlog SQL 注入：$db->query 拼接用户输入",
    },
    # 22. PDO 通用：$pdo->query / $pdo->exec 拼接（非预处理方式）
    {
        "id": "PDO_SQL",
        "regex": re.compile(
            r"pdo->(?:query|exec)\s*\(\s*[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "PDO SQL 注入：$pdo->query/exec 拼接用户输入（应使用 prepare）",
    },
    # 23. mysqli 通用：mysqli_query / $mysqli->query 拼接
    {
        "id": "MYSQLI_SQL",
        "regex": re.compile(
            r"(?:mysqli_query|mysqli->query)\s*\(\s*[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "mysqli SQL 注入：mysqli_query 拼接用户输入（应使用 bind_param）",
    },
    # 24. mysql 通用（已废弃）：mysql_query 拼接
    {
        "id": "MYSQL_DEPRECATED_SQL",
        "regex": re.compile(
            r"mysql_query\s*\(\s*[\"'].*?\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "mysql_query SQL 注入：已废弃 API + 拼接用户输入（极高风险）",
    },
    # === 框架特有风险（非 SQL 注入）===
    # 25. 反序列化漏洞：unserialize + 用户输入（所有 PHP 框架通用）
    {
        "id": "DESERIALIZE",
        "regex": re.compile(
            r"unserialize\s*\(\s*(?:\$_(?:GET|POST|REQUEST|COOKIE)\b"
            r"|file_get_contents\s*\(\s*\$_)",
            re.IGNORECASE
        ),
        "msg": "反序列化漏洞：unserialize 用户输入，可能导致 RCE",
    },
    # 26. 模板注入 - ThinkPHP：display/assign/fetch + 用户输入
    {
        "id": "TP_TEMPLATE_INJECT",
        "regex": re.compile(
            r"(?:this->assign|this->display|this->fetch)\s*\([^)]{0,80}"
            r"\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "ThinkPHP 模板注入：assign/display/fetch 含用户输入",
    },
    # 27. 模板注入 - Twig/Symfony：render + 用户输入
    {
        "id": "TWIG_INJECT",
        "regex": re.compile(
            r"(?:render|renderView|Twig::render)\s*\([^)]{0,80}"
            r"\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "Twig 模板注入：render 含用户输入",
    },
    # 28. 模板注入 - Blade/Laravel：Blade::compileString + 用户输入
    {
        "id": "BLADE_INJECT",
        "regex": re.compile(
            r"Blade::compileString\s*\([^)]{0,80}\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "Laravel Blade 模板注入：compileString 含用户输入",
    },
    # 29. SSRF：file_get_contents/curl_exec + 用户输入 URL
    {
        "id": "SSRF",
        "regex": re.compile(
            r"(?:file_get_contents|curl_exec|fopen|readfile)\s*\(\s*"
            r"(?:\$_(?:GET|POST|REQUEST)\b"
            r"|\$[a-z_]\w*\s*\.\s*\$_(?:GET|POST|REQUEST)\b)",
            re.IGNORECASE
        ),
        "msg": "SSRF/任意文件读取：file_get_contents/curl_exec 含用户输入",
    },
    # 30. XXE：simplexml_load_string/DOMDocument + 用户输入
    {
        "id": "XXE",
        "regex": re.compile(
            r"(?:simplexml_load_string|DOMDocument|XMLReader|xml_parse)\s*\(\s*"
            r"(?:\$_(?:GET|POST|REQUEST)\b"
            r"|\$[a-z_]\w*\s*\.\s*\$_(?:GET|POST|REQUEST)\b)",
            re.IGNORECASE
        ),
        "msg": "XXE 漏洞：XML 解析器含用户输入，可能读取服务器文件",
    },
    # 31. 代码执行：preg_replace /e 修饰符（PHP < 7）
    {
        "id": "PREG_E_EXEC",
        "regex": re.compile(
            r"preg_replace\s*\([^)]*['\"][^'\"]*[a-z]?e[a-z]?['\"]",
            re.IGNORECASE
        ),
        "msg": "代码执行：preg_replace 使用 /e 修饰符（PHP<7 代码执行）",
    },
    # 32. 代码执行：create_function（PHP < 8，已废弃）
    {
        "id": "CREATE_FUNCTION",
        "regex": re.compile(
            r"create_function\s*\(",
            re.IGNORECASE
        ),
        "msg": "代码执行：create_function 已废弃（PHP 8+ 移除），存在注入风险",
    },
    # 33. ThinkPHP 特有：I() 函数未过滤直接入 SQL
    {
        "id": "TP_I_SQL",
        "regex": re.compile(
            r"(?:empire->query|db->query|Db::query)\s*\([^)]{0,80}"
            r"\bI\(['\"](?:get|post|request|param)\.",
            re.IGNORECASE
        ),
        "msg": "ThinkPHP SQL 注入：I() 函数结果直接入 SQL（需 where 条件绑定）",
    },
    # 34. Laravel 特有：Artisan::call + 用户输入（命令注入）
    {
        "id": "ARTISAN_INJECT",
        "regex": re.compile(
            r"Artisan::call\s*\([^)]{0,80}\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "Laravel 命令注入：Artisan::call 含用户输入",
    },
    # 35. CodeIgniter 特有：$this->load->view + 用户输入模板名
    {
        "id": "CI_VIEW_INJECT",
        "regex": re.compile(
            r"this->load->view\s*\(\s*\$_(?:GET|POST|REQUEST)\b",
            re.IGNORECASE
        ),
        "msg": "CodeIgniter 模板注入：load->view 含用户输入模板名",
    },
    # 36. Yii 特有：unserialize + 用户输入（Yii 反序列化漏洞高发）
    {
        "id": "YII_DESERIALIZE",
        "regex": re.compile(
            r"unserialize\s*\(\s*(?:\$request->(?:get|post|body)\b"
            r"|\$_(?:GET|POST|REQUEST)\b)",
            re.IGNORECASE
        ),
        "msg": "Yii 反序列化漏洞：unserialize 用户输入",
    },
    # 37. 文件写入 + 用户输入路径（任意文件写入）
    {
        "id": "FILE_WRITE",
        "regex": re.compile(
            r"(?:file_put_contents|fwrite|fputs)\s*\(\s*"
            r"(?:\$_(?:GET|POST|REQUEST)\b"
            r"|\$[a-z_]\w*\s*\.\s*\$_(?:GET|POST|REQUEST)\b)",
            re.IGNORECASE
        ),
        "msg": "任意文件写入：file_put_contents/fwrite 路径含用户输入",
    },
]

# 安全函数正则（用于过滤误报）
SAFE_RE = re.compile("|".join(SAFE_FUNC), re.IGNORECASE)


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

    if not path.lower().endswith(TARGET_EXT):
        return 0

    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return 0

    # 中间变量污点追踪：收集被赋值为用户输入的变量，用于跨行 LFI 检测
    #   $page = $_GET['page']; include($page);
    taint_assign_re = re.compile(
        r"\$([A-Za-z_]\w*)\s*=\s*"
        r"(?:\$_(?:GET|POST|REQUEST|COOKIE)\b"
        r"|\$[A-Za-z_]\w*\s*\.\s*\$_(?:GET|POST|REQUEST|COOKIE)\b)",
        re.IGNORECASE,
    )
    tainted_vars = set()
    for line in lines:
        for m in taint_assign_re.finditer(line):
            tainted_vars.add(m.group(1))

    hits = []
    for i, line in enumerate(lines, 1):
        # 跳过注释行
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("#"):
            continue
        if stripped.startswith("/*") or stripped.startswith("*"):
            continue

        # 跳过包含安全函数的行
        if SAFE_RE.search(line):
            continue

        for pat in PATTERNS:
            if pat["regex"].search(line):
                hits.append((i, pat["id"], pat["msg"], stripped[:120]))

    # 中间变量 LFI：include/require 的参数是被用户输入赋值过的变量
    if tainted_vars:
        inter_include_re = re.compile(
            r"(?:include|require|include_once|require_once)\s*\(?\s*"
            r"\$(" + "|".join(re.escape(v) for v in sorted(tainted_vars, key=len, reverse=True)) + r")\b",
            re.IGNORECASE,
        )
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("#"):
                continue
            if stripped.startswith("/*") or stripped.startswith("*"):
                continue
            if SAFE_RE.search(line):
                continue
            if inter_include_re.search(line):
                hits.append((i, "FILE_INCLUDE",
                    "文件包含漏洞：include/require 使用被用户输入赋值过的中间变量，可能导致 LFI/RFI",
                    stripped[:120]))

    if not hits:
        return 0

    print("[CMS-RISK] 检测到 %d 处 CMS 高危风险 (%s):" % (len(hits), path))
    for line_no, risk_id, msg, code in hits[:20]:
        print("  L%d [%s] %s" % (line_no, risk_id, msg))
        print("    > %s" % code)
    if len(hits) > 20:
        print("  ... 还有 %d 处" % (len(hits) - 20))
    print("[CMS-RISK] 建议使用预处理语句/参数绑定/转义函数修复")
    return 1


if __name__ == "__main__":
    sys.exit(main())
