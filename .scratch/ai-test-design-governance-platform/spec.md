Status: ready-for-agent

# AI 测试设计与治理平台 V1 实施规格

## Problem Statement

测试工程师面对多格式、多版本的需求资料时，通常要在需求评审、范围与风险分析、用例设计、组织 Excel 模板、
人工与自动化结果之间反复搬运信息。普通的 AI 用例生成只能产出一次性文本，无法证明需求依据、解释风险和自动化价值，
也无法在需求变化、复测或结果冲突后持续维护测试资产。

本项目需要以洁净重写方式建立第二个独立作品项目。它必须完整覆盖“需求进入—AI 建议—人工确认—用例发布—任务导出—
结果回流—变更与回归治理”的首版闭环，同时严格保持与测试执行与诊断平台的职责边界。平台不能读取或复制原公司旧项目
资产，也不能把设备控制、数据生成、多模态检查器或完整自动化执行能力带入本项目。

## Solution

建设一个供单个本地测试工程师使用的测试设计与治理平台。测试工程师围绕测试对象创建测试设计项目，导入多格式需求资料
并形成不可覆盖的需求版本；平台通过可审计 AI 运行辅助提取原子需求、识别需求评审发现、分析项目测试维度、测试范围项、
风险项和自动化候选，再由测试工程师通过需求确认和设计确认关口决定正式资产。

平台接受多工作表 XLSX 和 CSV 用例模板，经逐表工作表角色、标题行和模板映射确认后生成候选测试用例。产品经理评审员、
测试经理评审员和项目经理评审员进行相互隔离的独立评审，测试工程师逐条处置 AI 评审建议并形成不可覆盖的用例修订版本。
已确认用例既可按原模板单独下载，也可在发布确认后生成通用 JSON/YAML 测试任务，并通过执行适配器转换为特定执行目标契约。

平台创建执行批次并导入多份人工结果输入和自动化结果输入，不在本地执行设备、浏览器或项目一检查器。它保留每次用例执行
记录、复测关系、执行异常、阻塞和结果冲突，由测试工程师确认批次结论。确定性规则计算可展开的覆盖指标并形成回归候选集；
V2 需求版本到来后，平台分析需求变更及变更影响，由人工完成用例状态治理和回归选择。

所有 AI 输出先经过结构校验再进入人工确认流程。AI 不能决定需求事实、执行结论或自动越过四个人工确认关口。真实模型服务
与确定性 Mock 通过独立边界接入；演示使用从零创作的合成需求包和隔离的评估真值，并以资产来源记录证明洁净重写。

## User Stories

1. As a 测试工程师, I want to create a 测试设计项目 for a named 测试对象, so that all requirement, design, review, task, and result assets share one governed context.
2. As a 测试工程师, I want the platform to remain independent of any particular device or product type, so that the same workflow can serve APIs, Web systems, mobile applications, services, or devices.
3. As a 测试工程师, I want to record a 测试对象 description and project-level settings, so that later AI analysis receives explicit, bounded context.
4. As a 测试工程师, I want to import multiple 需求资料 into one 需求资料包, so that product requirements, rules, interfaces, and screenshots can be reviewed together.
5. As a 测试工程师, I want to import Markdown, TXT, DOCX, text-extractable PDF, JSON, YAML, OpenAPI, PNG, and JPG inputs, so that common requirement formats enter one workflow.
6. As a 测试工程师, I want unsupported, unreadable, oversized, or partially extractable inputs to produce explicit diagnostics, so that missing content is never silently treated as complete.
7. As a 测试工程师, I want each accepted 需求资料包 to create an immutable 需求版本, so that later design assets can be reproduced and compared.
8. As a 测试工程师, I want original files, extracted content, hashes, and parsing outcomes preserved as auditable input facts, so that AI output can be traced back to its source.
9. As a 测试工程师, I want AI to propose 原子需求 with 需求来源引用, so that compound statements become independently reviewable without rewriting original material.
10. As a 测试工程师, I want confirmed 原子需求 to receive a 稳定需求 ID, so that the same requirement can be tracked across 需求版本.
11. As a 测试工程师, I want to split, merge, edit, accept, or reject 原子需求 candidates before 需求确认, so that AI suggestions do not become facts automatically.
12. As a 测试工程师, I want screenshot-derived content marked as 视觉推断, so that visual clues remain candidates until explicitly confirmed.
13. As a 测试工程师, I want AI to identify 需求评审发现 such as ambiguity, omission, conflict, untestability, missing acceptance criteria, unclear dependencies, missing constraints, and missing exception handling, so that requirement quality issues are visible early.
14. As a 测试工程师, I want every 需求评审发现 to have a type, status, rationale, and source or inference marker, so that its treatment is reviewable.
15. As a 测试工程师, I want to move a 需求评审发现 through 待确认、已采纳、已拒绝、待外部确认、已解决 or 接受风险, so that unresolved questions and accepted uncertainty remain explicit.
16. As a 测试工程师, I want a 需求确认 gate over 原子需求、视觉推断 and 需求评审发现, so that unconfirmed content cannot become the formal basis for design.
17. As a 测试工程师, I want a configurable hierarchy of 项目测试维度 seeded from common 测试维度, so that scope can reflect both general quality concerns and project-specific concerns.
18. As a 测试工程师, I want AI to propose 维度建议 without activating them, so that project classification changes only through 设计确认.
19. As a 测试工程师, I want to add, rename, move, merge, or deactivate dimensions while preventing deletion of referenced dimensions, so that historical traceability survives taxonomy changes.
20. As a 测试工程师, I want AI to propose 测试范围项 linked to confirmed 原子需求, so that planned verification has an explicit basis.
21. As a 测试工程师, I want each 测试范围项 to have one 主要测试维度 and optional 次要测试维度, so that cross-cutting concerns are visible without double-counting scope.
22. As a 测试工程师, I want AI to propose 风险项 and 风险建议分 with cited evidence and factor-level reasons, so that risk analysis is explainable.
23. As a 测试工程师, I want deterministic rules to calculate 最终风险分 and 风险等级 from confirmed 风险因子, so that identical inputs produce identical priorities.
24. As a 测试工程师, I want to adjust a 风险因子 value only with a recorded reason, so that human judgment is retained without hiding overrides.
25. As a 测试工程师, I want 测试优先级 P0–P3 to reflect risk, business criticality, requirement change, and historical results, so that execution order is governable.
26. As a 测试工程师, I want AI to assess 自动化候选 separately from risk, so that a high-risk scenario is not incorrectly assumed to be automatable.
27. As a 测试工程师, I want 自动化建议 to explain regression value, determinism, environment controllability, data cost, time benefit, stability, development cost, maintenance cost, and required human or specialist observation, so that trade-offs are visible.
28. As a 测试工程师, I want to confirm an 自动化决定 as 优先自动化、适合自动化、条件满足后自动化 or 保留人工执行, so that AI cannot commit automation work.
29. As a 测试工程师, I want multiple independent 测试用例 to map to one 自动化实现映射 while retaining separate 稳定用例 ID results, so that parameterization does not erase test identity.
30. As a 测试工程师, I want a 设计确认 gate over dimensions, scope, risk, priority, and automation candidates, so that only reviewed design assets can drive case generation.
31. As a 测试工程师, I want to upload a multi-sheet XLSX 用例模板 or a CSV template, so that platform output fits an external organizational format.
32. As a 测试工程师, I want AI to suggest each 工作表角色 as 用例表、说明表、字典表、统计表 or 未知, so that mixed-purpose workbooks can be processed safely.
33. As a 测试工程师, I want to confirm which sheets participate, each title row, and each sheet-specific 模板映射, so that different 用例表 structures are supported without guessing.
34. As a 测试工程师, I want every 测试用例 to have one 用例归属表, so that cross-sheet imports and coverage statistics do not duplicate it.
35. As a 测试工程师, I want non-participating sheets retained during export, so that instructions, dictionaries, and supporting workbook content are not discarded.
36. As a 测试工程师, I want unsupported formulas, macros, images, merged cells, or pivot behavior reported before export, so that formatting loss is never silent.
37. As a 测试工程师, I want the internal 测试用例 model to represent ordered 测试步骤、逐步预期 and 整体预期, so that external template differences do not weaken test meaning.
38. As a 测试工程师, I want one clear input, boundary, equivalence class, or scenario per independently numbered 测试用例, so that execution and governance remain precise.
39. As a 测试工程师, I want AI-generated candidates to retain 用例设计依据 internally, so that I can review test methods without leaking them into the final 用例文件.
40. As a 测试工程师, I want candidate cases to trace to confirmed requirements, scope, risks, priorities, and evidence requirements, so that generated volume can be assessed for relevance.
41. As a 测试工程师, I want 产品经理评审员、测试经理评审员 and 项目经理评审员 to run independently on the same candidate version, so that each role contributes a distinct perspective without seeing the others' output.
42. As a 测试工程师, I want each role's AI 评审建议 to retain its role source even after duplicate grouping, so that consolidation does not erase accountability.
43. As a 测试工程师, I want to accept, reject, or modify every AI 评审建议, so that the final case set represents an explicit human decision.
44. As a 测试工程师, I want accepted suggestions to create an immutable 用例修订版本 instead of overwriting candidates, so that the review path is auditable.
45. As a 测试工程师, I want a 用例确认 gate to finalize the revision and 用例纳入决定, so that no AI review result publishes itself.
46. As a 测试工程师, I want first-confirmed cases to receive a 稳定用例 ID while retaining any 外部用例编号, so that internal identity is stable without breaking template compatibility.
47. As a 测试工程师, I want fundamental test-target changes to create a new ID and mark the old case as 被替代用例 with a successor link, so that distinct test definitions are not disguised as revisions.
48. As a 测试工程师, I want 用例生命周期 and 当前测试参与状态 managed independently, so that long-term validity is not confused with whether a case runs this round.
49. As a 测试工程师, I want every 用例状态变更 to record previous state, new state, reason, time, and confirmer, so that AI suggestions cannot silently rewrite governance history.
50. As a 测试工程师, I want to download a 用例文件 independently of task, report, or audit exports, so that test cases remain a standalone deliverable.
51. As a 测试工程师, I want 用例导出范围 to support all current cases, manually selected cases, or cases added or changed since the previous 需求版本, so that different delivery needs do not require editing the source workbook.
52. As a 测试工程师, I want exports to default to the latest confirmed, included revisions and exclude 用例设计依据, so that delivery is safe and unambiguous.
53. As a 测试工程师, I want a generic 测试任务 model containing task identity, case references, target, priority, prerequisites, parameters, expected result, verdict method, and evidence requirements, so that execution requests are portable.
54. As a 测试工程师, I want generic 测试任务 to export as versioned JSON or YAML validated by schema, so that external consumers receive a stable contract.
55. As a 测试工程师, I want 执行目标-specific fields isolated in 目标扩展, so that the common domain model does not become tied to one executor.
56. As a 测试工程师, I want an 执行适配器 to transform generic tasks and 运行结果反馈 to and from a target contract, so that the 测试执行与诊断平台 can be the first integration without owning platform rules.
57. As a 测试工程师, I want a 发布确认 gate over execution scope, target, and target extension, so that no JSON/YAML task is released without human approval.
58. As a 测试工程师, I want to create an 执行批次 with product version, 需求版本, environment, test scope, responsible person, execution target, and immutable case revision snapshots, so that imported results have an explicit comparison context.
59. As a 测试工程师, I want the platform to preallocate the next 执行序号 for each included 稳定用例 ID, so that later imports cannot collide or overwrite history.
60. As a 测试工程师, I want an 执行展示编号 formed from 外部用例编号 and 执行序号 while retaining internal IDs separately, so that humans can read attempts without weakening identity.
61. As a 测试工程师, I want to export an artificial execution file for a batch, so that manual results can be collected consistently outside the platform.
62. As a 测试工程师, I want one 执行批次 to accept multiple 人工结果输入 and 自动化结果输入 files, so that distributed execution can be consolidated incrementally.
63. As a 测试工程师, I want imports to associate results by stable ID and revision first, registered external number second, and explicit manual matching last, so that ambiguous data is never guessed into place.
64. As a 测试工程师, I want every retry or repeated test to create a new 用例执行记录 and explicit 复测关系, so that earlier facts remain intact.
65. As a 测试工程师, I want execution states to distinguish 通过、执行失败、阻塞、未执行 and 执行异常, so that product failure is not confused with missing or invalid execution.
66. As a 测试工程师, I want initial result, latest result, and human-confirmed 批次结论 shown together, so that retesting history is not collapsed into one status.
67. As a 测试工程师, I want comparable human and automated differences to become a 结果冲突, so that neither AI nor import order automatically decides the truth.
68. As a 测试工程师, I want to resolve each 结果冲突 with a recorded decision and reason, so that the batch conclusion is auditable.
69. As a 测试工程师, I want lightweight 质量问题引用 linked to evidence, severity, external defect number, status, release impact, fix version, and retest, so that findings support governance without recreating a defect system.
70. As a 测试工程师, I want AI to propose 缺陷模式 from multiple quality issues while clearly avoiding root-cause claims, so that recurring symptoms can inform regression selection safely.
71. As a 测试工程师, I want 需求覆盖率、风险覆盖率、测试维度覆盖、执行覆盖率 and 自动化覆盖率 to show numerator, denominator, and uncovered details, so that dashboard percentages can be verified.
72. As a 测试工程师, I want semantic similarity to remain a relationship suggestion rather than a coverage fact, so that AI resemblance does not inflate governance metrics.
73. As a 测试工程师, I want deterministic rules to create a 回归候选集 from requirement changes, high risk, historical failures or exceptions, result conflicts, open quality issues, defect patterns, adjacent state paths, and long-unexecuted cases, so that the baseline is reproducible.
74. As a 测试工程师, I want AI to add reasoned regression suggestions without removing deterministic candidates, so that useful context can supplement but not replace rules.
75. As a 测试工程师, I want to confirm a 回归选择 with inclusion or exclusion reasons, so that the final regression scope remains a human decision.
76. As a 测试工程师, I want to import a V2 需求资料包 as a new immutable 需求版本, so that V1 assets and results remain reproducible.
77. As a 测试工程师, I want AI to propose added, modified, deleted, split, merged, and continued 原子需求 between V1 and V2, so that change analysis is structured.
78. As a 测试工程师, I want to confirm each 需求变更 before it affects formal assets, so that an AI comparison cannot rewrite traceability.
79. As a 测试工程师, I want 变更影响 to identify related scope, risk, cases, tasks, and regression candidates through existing trace paths, so that updates are targeted instead of regenerating everything.
80. As a 测试工程师, I want affected cases marked 待影响确认 until I choose to retain, revise, close, deprecate, replace, include, or exclude them, so that V2 governance is explicit.
81. As a 测试工程师, I want every AI 运行 to retain task type, model and parameters, Prompt 版本, input asset versions, structured output, validation outcome, timing, state, attempts, disposition, and Mock marker, so that AI behavior can be audited.
82. As a 测试工程师, I want schema-invalid AI output to remain an audit record but create no formal 测试设计资产, so that malformed model output cannot contaminate the workflow.
83. As a 测试工程师, I want retry limited to timeouts, rate limits, and temporary service errors, so that deterministic, authorization, content-safety, and schema errors do not loop without evidence.
84. As a 测试工程师, I want model failure to leave confirmed assets, deterministic statistics, imports, exports, and existing reports usable, so that the platform degrades safely.
85. As a 测试工程师, I want deterministic Mock AI 运行 for normal, empty, missing-reference, invalid-schema, and service-failure cases, so that local demonstrations and CI need no real model or API key.
86. As a 测试工程师, I want Mock results visibly marked in pages, reports, persistence, and the 审计包, so that synthetic behavior is never represented as real model performance.
87. As a 测试工程师, I want model credentials read only by the backend and excluded from persistence, logs, reports, API responses, and exports, so that secrets do not leak.
88. As a 测试工程师, I want each model call to receive only authorized, task-minimal context and never 来源不明资产, so that AI access follows the project safety boundary.
89. As a portfolio owner, I want a from-scratch 合成需求包 for a fictional 智能采集设备, so that the complete workflow can be demonstrated without old-company assets.
90. As a portfolio owner, I want V1 to contain 30–40 confirmed 原子需求, 10–15 seeded review issues, 15–25 risks, and 80–120 confirmed cases, so that evaluation covers realistic scale and variety.
91. As a portfolio owner, I want the V2 package to contain 8–12 planned additions, modifications, deletions, splits, merges, interface changes, and indirect regression effects, so that change governance has known expected behavior.
92. As a portfolio owner, I want at least three independent synthetic result inputs covering all statuses, failure-then-pass retest, and one result conflict, so that result governance is demonstrable end to end.
93. As a portfolio owner, I want 评估真值 to remain isolated from normal model calls while recording expected review issues, scope, risks, change impacts, and distractors, so that AI quality can be assessed without answer leakage.
94. As a portfolio owner, I want every demo input, Mock output, and truth asset to have an 资产来源记录 with origin, rights, model permission, requirement version, and SHA-256, so that 洁净重写 is verifiable.
95. As a portfolio owner, I want AI quality reported through structural compliance, valid citations, 真值命中, key misses, 无依据扩展, and 人工采纳率, so that “generated many cases” is not treated as proof of quality.
96. As a 测试工程师, I want independent 测试设计报告、执行与治理报告 and 审计包 deliverables, so that design evidence, governance evidence, and audit evidence can be reviewed without coupling them to the 用例文件.

## Implementation Decisions

- V1 is a local, single-user system. 测试工程师 is the only real user role; AI reviewer names are perspectives, not accounts. A confirmer name may be recorded for audit without introducing authentication or authorization.
- The platform uses a browser-based user interface, a Python API service, local relational persistence, and local file storage. Domain behavior is exposed through explicit API contracts rather than embedded in the user interface.
- The domain is organized around 测试设计项目, immutable 需求版本, versioned 测试设计资产, independent AI 运行, immutable 用例修订版本, 执行批次, and append-only execution and decision history.
- Stable internal identifiers are authoritative. External document sections, template case numbers, display numbers, and file names remain references and never replace 稳定需求 ID、稳定用例 ID、测试任务 ID or execution-record identity.
- Original requirement assets and confirmed historical versions are never overwritten. Corrections or changes create a new version or explicit decision record.
- Requirement parsing is format-specific at the boundary and normalizes extracted text, structured content, tables, images, parsing diagnostics, hashes, and stable source locations. Screenshot-derived content remains 视觉推断 until confirmed.
- The first supported formats are Markdown, TXT, DOCX, text-extractable PDF, JSON, YAML, OpenAPI, PNG, and JPG. Long scanned-document OCR, video explanations, online document synchronization, and arbitrary proprietary formats are not promised.
- AI creates candidates and suggestions only. Deterministic rules own identifiers, schemas, formulas, state-transition validation, coverage calculations, execution numbering, import matching constraints, contract transformation, and audit timestamps.
- Four mandatory 人工确认关口 control progression: 需求确认, 设计确认, 用例确认, and 发布确认. Saving drafts is allowed, but an AI run cannot pass a gate or manufacture the corresponding confirmation.
- Project dimensions form a configurable hierarchy. A 范围项 has exactly one 主要测试维度 and zero or more 次要测试维度; coverage counts the range item once.
- Risk is factor-based and explainable. AI supplies 风险建议分, evidence, and reasons; the system calculates 最终风险分 and 风险等级 from a published rule; human adjustments require reasons.
- Automation suitability is modeled separately from risk. V1 records 自动化建议、自动化决定 and optional 自动化实现映射 but does not generate runnable automation scripts.
- The internal test-case model is independent of external templates and supports prerequisites, ordered steps, step expectations, overall expectation, priority, evidence requirements, traceability, and internal 用例设计依据.
- Multi-sheet XLSX handling first inventories workbook structure. Each selected 用例表 has its own confirmed title row and 模板映射. Non-participating sheets are preserved where feasible, and any unsupported workbook feature or lossy mapping is disclosed before export.
- A test case has one 用例归属表 and one explicit scenario. Different boundaries, equivalence classes, or data conditions remain independently identifiable cases even when one parameterized implementation may execute them.
- The three AI reviewer perspectives are separate AI 运行 with least context required for the role and no access to one another's output. Duplicate grouping occurs only after all three complete and must retain every role source.
- Accepting or modifying an AI 评审建议 produces a new 用例修订版本. First confirmation assigns a 稳定用例 ID; a fundamentally changed test objective creates a new ID and an explicit replacement relationship.
- 用例生命周期 and 当前测试参与状态 are independent state machines. Every state decision is human-controlled and audited; replacement requires a successor, deprecation requires a reason, and closure remains reversible.
- 用例文件 is a standalone delivery path. Default exports include only the latest confirmed and included revisions and exclude internal design rationale, AI review history, secrets, and task metadata unless the selected template explicitly owns a safe public field.
- In accordance with the existing ADR, the platform owns stable generic 测试任务 and 运行结果反馈 models. An 执行适配器 converts those contracts for a specific 执行目标, and target-only configuration remains in 目标扩展.
- JSON and YAML contracts are versioned and schema-validated. The 测试执行与诊断平台 is the first target adapter but does not enter the generic domain model and is not required for the platform's standalone demonstration.
- An 执行批次 snapshots product version, 需求版本, environment, scope, responsible person, target, and included case revisions. Execution sequence numbers are allocated before export and cannot be reused to overwrite a record.
- Result import is append-only and idempotent for an identical source record. Association precedence is stable internal identity and revision, registered external number, then explicit manual matching; low-confidence matches remain unresolved.
- 通过 and 执行失败 are valid test conclusions. 阻塞、未执行 and 执行异常 are distinct non-equivalent states. Retesting creates a new record and 复测关系; it never mutates the earlier record.
- Initial result, latest result, and 批次结论 are stored and presented separately. A 结果冲突 blocks automatic conclusion and requires a human decision with rationale.
- V1 quality issue support is deliberately lightweight. 质量问题引用 and 缺陷模式 support evidence, release impact, retest, and regression decisions without implementing assignment, workflow, SLA, discussion, or other full defect-system behavior.
- Coverage facts require confirmed traceability. All five metrics expose numerator, denominator, and missing details. Semantic similarity and AI suggestions cannot directly establish coverage.
- Regression candidates begin with deterministic rules and may receive additive AI suggestions. 回归选择 remains a recorded human decision.
- V1→V2 comparison proposes requirement continuity and change types, but a human confirms 需求变更 before 变更影响 changes any governed state. Existing V1 assets and results remain reproducible.
- Each AI task has a versioned structured-output contract. Invalid output is retained only as an AI audit event. Limited retry applies only to recoverable service errors and each attempt preserves evidence.
- The model-service boundary supports a real configured provider and deterministic Mock. CI and the default offline demonstration use Mock and require no model credential.
- Model credentials are backend-only environment configuration. Audit data records Prompt 版本 and input summaries, not credentials or complete confidential prompt content.
- Every model request uses the minimum authorized context. 来源不明资产 and 评估真值 are excluded from normal model calls. Mock and real AI outcomes remain visibly distinguishable.
- Demo assets are created from scratch for a fictional 智能采集设备 and recorded through 资产来源记录. No code, Prompt, page, screenshot, requirement, interface, threshold, defect, result, or unpublished information from the original company project may be read, copied, renamed, or “desensitized” into this project.
- The V1 product flow is complete only when a user can traverse project creation, V1 requirement confirmation, design confirmation, template mapping, case generation, three-role review, case confirmation and download, task publication, multi-result import, conflict/retest governance, V2 impact analysis, and regression selection.
- Roadmap items after V1 are not acceptance criteria and must not be represented as implemented work.

## Testing Decisions

- Tests assert externally observable behavior: API responses, persisted version/history behavior, accepted and rejected state transitions, generated files and contracts, import outcomes, audit records, and user-visible workflow completion. They do not assert private function calls, component internals, SQL shape, or implementation-specific module layout.
- The primary test seam is the FastAPI application/API boundary. End-to-end backend tests create a project, upload versioned inputs, drive the four confirmation gates, generate and revise cases, publish tasks, import results, resolve conflicts, apply V2 changes, and confirm regression selection through public APIs.
- API tests cover successful behavior, validation failures, permissions implied by the single-user safety model, immutable-history guarantees, idempotency, ambiguous matching, invalid state transitions, partial failure, and safe recovery after model or file errors.
- The necessary secondary file seam is contract round-trip testing for requirement imports, XLSX/CSV template mapping, 用例文件 export, manual result files, JSON/YAML tasks, result imports, reports, and audit packages.
- Multi-sheet XLSX tests verify sheet-role confirmation, different per-sheet mappings, title rows, single 用例归属表, retention of unselected sheets, stable case identity, no internal rationale leakage, and explicit diagnostics for unsupported or lossy workbook features.
- The necessary secondary adapter seam is contract round-trip testing between the generic 测试任务/运行结果反馈 model and each supported 执行目标 contract. A generic task transformed to the first target and a compatible result transformed back must retain stable identity, revision, execution sequence, verdict meaning, and evidence references.
- Schema tests verify every AI output, task contract, target contract, result input, report data contract, and audit export with valid, missing, extra, malformed, and version-mismatch cases.
- Deterministic domain tests verify risk formulas, automation suitability formulas, unique IDs, state-transition guards, coverage numerators and denominators, regression rules, result ordering, execution-sequence allocation, idempotent import, and conflict detection.
- AI behavior tests use deterministic Mock responses at the API seam. They cover valid output, empty output, missing source references, invalid schema, timeout, rate limit, temporary service error, authentication error, content-safety error, exhausted retry, and successful manual retry.
- AI audit tests verify role isolation, input-version capture, Prompt 版本, Mock marking, attempt history, schema outcome, human disposition, no automatic gate crossing, and continued deterministic operation while the model is unavailable.
- Security tests verify model credentials never appear in API payloads, persistence, logs, generated files, reports, or audit packages; unauthorized or 来源不明资产 is excluded from model input; 评估真值 is isolated from normal generation context.
- Versioning tests verify immutable 需求版本 and 用例修订版本, cross-version stable IDs, replacement rules, V1 reproducibility after V2, confirmed change types, and explicit state/history records.
- Result-governance tests import at least three files and verify 通过、执行失败、阻塞、未执行、执行异常, failure-to-pass retest, duplicate input, unresolved mapping, one human/automation 结果冲突, and a human-confirmed 批次结论 without history loss.
- Coverage tests verify all five metrics against inspectable fixture data and assert the displayed numerator, denominator, covered items, and gaps—not only the percentage.
- Regression tests verify that deterministic candidates cannot be removed by AI, AI suggestions carry reasons and are deduplicated, invalid or inactive cases are excluded, and final 回归选择 is human-confirmed.
- Frontend tests cover only critical user journeys and visible guardrails: the four confirmation gates, sheet mapping, three-role suggestion disposition, standalone case download, task publication, multi-result conflict handling, and V1→V2 regression confirmation. They do not test component state, hooks, DOM structure beyond accessibility contracts, or other internal implementation details.
- Existing project evidence is currently design documentation rather than implemented test prior art. New tests should follow the planned Pytest API/contract style and lightweight critical-flow frontend style documented in the project, while keeping the FastAPI seam as the dominant source of confidence.
- Acceptance uses the from-scratch synthetic V1/V2 package, isolated evaluation truth, template workbook, and three result inputs. CI uses Mock only and must not call a real model or require an API key.

## Out of Scope

- Generating complete runnable Pytest, API, UI, device, or browser automation scripts.
- Controlling devices, browsers, operating-system UI, external environments, or test data collection hardware.
- Generating or collecting video, audio, IMU, status, logs, or other execution evidence.
- Implementing video, IMU, synchronization, file-integrity, multimodal, or other deterministic checkers owned by the 测试执行与诊断平台.
- Reimplementing the 测试执行与诊断平台, embedding its domain model, or making it mandatory for standalone operation.
- A generic local Pytest executor, browser executor, scheduler, environment provisioner, or unrestricted autonomous coding agent.
- A complete defect-management system, including assignment workflow, SLA, comments, notifications, approval, and organization-wide analytics.
- Authentication, real user accounts, teams, roles, permissions, multi-user concurrency, collaborative editing, notifications, or formal approval workflow.
- Online document synchronization, Jira/禅道 integration, organizational requirement systems, or arbitrary third-party integrations.
- Complete OCR for arbitrary scanned documents, video requirement transcription, or support for arbitrary proprietary formats.
- Guaranteed lossless editing of complex formulas, macros, embedded images, merged cells, data-pivot features, or every workbook styling feature.
- Automatic approval of requirement facts, design decisions, test cases, release, execution verdicts, result conflicts, defect root causes, or regression scope.
- Treating semantic similarity, AI confidence, or AI prose as a confirmed coverage relationship or deterministic calculation.
- Reading, copying, adapting, anonymizing, or migrating any original-company code, Prompt, page, data, document, interface, threshold, defect, screenshot, or unpublished information.
- V1.1 template reuse and expanded adapters, V2 automation code generation, V2.1 execution/scheduling, and V3 external collaboration capabilities described in the roadmap.

## Further Notes

- This document is the agent-ready implementation specification for V1. It synthesizes the confirmed project documents and does not supersede the formal vocabulary in `CONTEXT.md` or the existing ADR.
- V1 acceptance requires one demonstrable closed loop: create a 测试设计项目; import and confirm V1; confirm dimensions, scope, risk, and automation decisions; map a multi-sheet template; generate and independently review cases; confirm and download a 用例文件; publish a schema-valid task; create a batch and import multiple results; resolve retest, exception, blocking, and conflict; import V2; confirm change impact and regression selection.
- Acceptance also requires auditable evidence that requirement/source links, all four gates, AI runs and dispositions, case versions and states, execution histories, coverage details, asset provenance, Mock labels, and secret exclusions behave as specified.
- The synthetic asset set is part of V1 validation, not a source of production truth. It must use fictional names, rules, interfaces, values, identifiers, and results; its independent 评估真值 must never enter ordinary model context.
- Delivery claims must remain “planned” until reproducible tests, generated artifacts, and demonstration evidence exist. Later roadmap capabilities must not be counted toward V1 acceptance.

## Comments

- 2026-08-24: Synthesized from the confirmed project specification, domain vocabulary, AI workflow, course coverage, project introduction, interview case, roadmap, synthetic requirement plan, asset provenance rules, and existing ADR. Published directly as `ready-for-agent` without additional triage or implementation.
