# Output Schemas

Use these schemas to keep legal outputs consistent and auditable.

## Contract Review

```yaml
合同摘要:
  合同类型:
  当事人:
  金额/期限:
  履约路径:
  保护立场:
风险摘要:
  高风险:
  中风险:
  低风险:
逐条审查:
  - 条款:
    原文摘要:
    问题类型: [法律风险, 商业风险, 证据风险, 执行风险, 合规风险]
    风险等级: HIGH | MEDIUM | LOW
    依据:
      - 名称:
        条款/案号:
        链接或来源:
    修改建议:
    建议替代条款:
    谈判底线:
缺失条款:
需业务确认:
人工复核:
免责声明:
```

## Contract Drafting

```yaml
起草前假设:
合同正文:
  标题:
  条款:
    - 条款名:
      内容:
风险说明:
  偏甲方条款:
  偏乙方条款:
  需确认事项:
履约清单:
  - 时间:
    动作:
    责任方:
    留存证据:
人工复核:
免责声明:
```

## Legal Consultation

```yaml
结论摘要:
事实假设:
待确认事实:
Issue问题:
Rule依据:
Application分析:
Conclusion结论:
风险分级:
行动清单:
证据/流程建议:
人工复核:
免责声明:
```

## Compliance Check

```yaml
业务流程摘要:
监管规则:
内部规则:
缺口与风险:
整改建议:
责任岗位:
完成时限:
需升级事项:
免责声明:
```

