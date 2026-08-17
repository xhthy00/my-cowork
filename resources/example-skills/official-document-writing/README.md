# Official Document Writing Skill Project

## Project Overview

This is a professional Skill toolkit for writing Chinese Party and government official documents (公文). It strictly follows the national standard **GB/T 9704-2012 _Format of Official Documents of Party and Government Organs_**, and provides complete writing guidance, templates, examples, and a quality checklist.

This project is optimized based on Claude Code’s official **skill-creator** framework and adopts the **progressive disclosure** design approach, offering efficient and professional support for official-document writers.

---

## 📊 Project Snapshot

- **Project Name**: official-document-writing-skill  
- **Created**: January 2026  
- **Skill Version**: v1.0  
- **Standard Reference**: GB/T 9704-2012 _Format of Official Documents of Party and Government Organs_  
- **Core Capabilities**: official document drafting, format compliance checking, template usage, writing guidance  
- **Target Users**: staff in Party/government organs, administrative secretarial staff in enterprises and institutions, learners of official writing

---

## 🎯 Key Features

### 1. Format & Compliance Guidance
Based on GB/T 9704-2012, the toolkit provides:
- Complete formatting requirements (paper, layout, fonts, font sizes)
- Detailed typesetting rules (header section, main body, footer/colophon)
- Special format notes (letter format, orders/decrees, meeting minutes)
- Rules for page numbers, tables, and units of measurement

### 2. Official Document Template Library
Provides standard templates for 6 common document types and **30+ real-world examples**:
- ✅ Request for Instructions/Approval (请示) — 3 examples  
- ✅ Notice (通知) — 4 examples (incl. meetings, training, forwarding)  
- ✅ Letter (函) — 4 examples (incl. coordination, approval request, replies)  
- ✅ Summary (总结) — 6 examples (incl. work summaries, experience summaries)  
- ✅ Meeting Minutes (会议纪要) — 2 examples (incl. Party committee meetings, office meetings)  
- ✅ Report (报告) — 1 detailed example  

### 3. Writing Techniques Guide
- Four principles of official language: **accuracy, plainness, conciseness, and formality**
- “Six checks” standard for crafting titles
- “Four-step method” for extracting experience
- 80+ common mistakes with corrections
- 50+ standardized phrases and expressions

### 4. Quality Checklist
100+ quality checkpoints covering:
- Format checks (40+ items)
- Content checks (30+ items across 5 document types)
- Language checks (40+ items)
- Logic checks (10+ items)
- Detail checks (20+ items)
- Final pre-issuance confirmation (10+ items)

---

## 📁 Repository Structure

```text
Official Document Writing Skill Project/
│
├── 📄 README.md                           # Project documentation (this file)
│
├── 📄 SKILL.md                            # Core navigation (635 lines)
│   ├── Use cases (5 major scenarios)
│   ├── Core workflow
│   ├── Formatting guidance
│   ├── Template navigation for common document types
│   ├── Language and writing norms
│   └── Quality checklist navigation
│
├── 📂 references/                         # Detailed references (progressive disclosure)
│   │
│   ├── 📄 gb-t-9704-2012-standard.md      # National standard explained (522 lines)
│   │   ├── Paper requirements
│   │   ├── Layout specifications
│   │   ├── Font and size rules
│   │   ├── Element arrangement rules
│   │   └── Special format requirements
│   │
│   ├── 📄 document-templates.md           # Template library (1,215 lines)
│   │   ├── Request templates + 3 examples
│   │   ├── Notice templates + 4 examples
│   │   ├── Letter templates + 4 examples
│   │   ├── Summary templates + 6 examples
│   │   ├── Meeting minutes templates + 2 examples
│   │   └── Report templates + 1 example
│   │
│   └── 📄 writing-techniques.md           # Writing techniques guide (761 lines)
│       ├── Four principles of official language
│       ├── Common standardized expressions
│       ├── Title drafting techniques
│       ├── Four-step method for extracting experience
│       ├── Common error corrections
│       └── Advanced writing tips
│
├── 📂 checklists/                         # Checklists
│   └── 📄 quality-checklist.md            # Quality checklist (396 lines)
│       ├── Format checks (40+ items)
│       ├── Content checks (30+ items)
│       ├── Language checks (40+ items)
│       ├── Logic checks (10+ items)
│       ├── Detail checks (20+ items)
│       └── Pre-issuance confirmation (10+ items)
│
├── 📂 templates/                          # Blank templates (reserved)
│   └── (Place .docx/.xlsx template files here)
│
├── 📂 scripts/                            # Utility scripts (reserved)
│   └── (Place Python/bash automation scripts here)
│
└── 📄 党政公文格式.txt                    # Raw material: GB/T 9704-2012 source
```
---
## 🚀 Use Cases

### Scenario 1: Draft a New Official Document
**For**: drafting a document from scratch  
**Workflow**:
1. Consult `SKILL.md` to determine the document type
2. Navigate to `document-templates.md`
3. Choose the corresponding template
4. Fill in the content with guidance from the writing techniques
5. Verify with `quality-checklist.md`

### Scenario 2: Revise and Improve a Draft
**For**: optimizing an existing draft  
**Workflow**:
1. Check items one by one using `quality-checklist.md`
2. Mark any issues found
3. Consult `writing-techniques.md` for revision suggestions
4. Improve expression using template examples
5. Run a second review to confirm

### Scenario 3: Check Format Compliance
**For**: verifying whether the document format is correct  
**Workflow**:
1. Open `quality-checklist.md`
2. Verify each item in the format-check section
3. Cross-check with `gb-t-9704-2012-standard.md`
4. Mark non-compliant items
5. Fix and re-check

### Scenario 4: Learn Official Document Writing
**For**: beginners learning how to write official documents  
**Workflow**:
1. Read `SKILL.md` to understand the overall framework
2. Study the four principles in `writing-techniques.md`
3. Review cases in `document-templates.md`
4. Master key checklist points in `quality-checklist.md`
5. Practice and summarize experience

### Scenario 5: Quick Rule Lookup
**For**: quickly locating specific rules during work  
**Method**:
- Format → `gb-t-9704-2012-standard.md`
- Templates → `document-templates.md`
- Wording → `writing-techniques.md`
- Checklist items → `quality-checklist.md`

---

## ✨ Technical Highlights

### 1. Progressive Disclosure
Aligned with Claude Code skill design best practices:
- 🎯 **`SKILL.md`**: concise core (635 lines)
- 📚 **`references/`**: deep references (2,498 lines)
- ✅ **`checklists/`**: practical tools (396 lines)  
- **Benefits**: avoids information overload, loads on demand, improves efficiency

### 2. Standardized Design
- 📋 Strictly follows the GB/T 9704-2012 national standard
- 🎯 Compatible with the Claude Code `skill-creator` framework
- 📊 Standardized document structure and naming

### 3. Highly Practical
- 💼 30+ real workplace cases
- ✅ 100+ quality checkpoints
- 📝 50+ standardized phrases and expressions
- 🔧 Tools that can be applied directly in real work

### 4. Systematic and Complete
- From format to content to checking
- From fundamentals to advanced improvement
- From templates to techniques to examples
- A complete official-document writing system

---

## 🎯 Target Users

### Primary User Groups
1. **Secretarial staff in Party/government organs**
   - Daily official document drafting
   - Format compliance control

2. **Administrative staff in enterprises and institutions**
   - Requests and reports to higher authorities
   - Notices and guidance to subordinate units

3. **Learners of official-document writing**
   - Learn compliance requirements
   - Master writing techniques

4. **Official document reviewers/proofreaders**
   - Format and quality review
   - Standardized inspection

### Applicable Organizations
- Party and government organs at all levels
- Public institutions
- State-owned enterprises
- Private enterprises (external formal documents)
- Social organizations

---

## 💡 Best Practices

### Usage Suggestions

1. **Beginner Onboarding**
   ```text
   Start with SKILL.md → understand the overall framework
   ↓
   Study writing-techniques.md → master the core principles
   ↓
   Review document-templates.md → learn concrete examples
   ↓
   Use quality-checklist.md → master key inspection points
2. **Daily Use
   ```text
   While drafting → open SKILL.md to confirm the document type
   ↓
   Find templates → locate the relevant template in document-templates.md
   ↓
   When in doubt → consult gb-t-9704-2012-standard.md for rules
   ↓
   After completion → verify item-by-item with quality-checklist.md
3.**Quality Control
   Format → gb-t-9704-2012-standard.md
   ↓
   Content → document-templates.md (key points by document type)
   ↓
   Language → writing-techniques.md (the four principles)
   ↓
   Overall → quality-checklist.md (100+ items)

> 中文说明请见 [README.zh-CN.md](README.zh-CN.md)

