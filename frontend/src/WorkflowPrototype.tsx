import { type ReactNode, useState } from "react";

import "./workflow-prototype.css";

// PROTOTYPE — 用于确认一套前端信息架构；不连接后端或模型。

type TabId = "upload" | "analysis" | "suggestions" | "review" | "cases";
type RunMode = "direct" | "skill" | "local";

const tabs: Array<{ id: TabId; label: string; description: string }> = [
  { id: "upload", label: "上传文档", description: "上传并解析资料，本页不调用 AI" },
  { id: "analysis", label: "需求分析", description: "识别功能点、测试项和测试点，并选择测试范围" },
  { id: "suggestions", label: "新增建议", description: "让 AI 补充遗漏的测试点" },
  { id: "review", label: "审核", description: "可选的三个 AI 身份审核" },
  { id: "cases", label: "测试用例", description: "选择模板、生成、预览与下载" },
];

const analysisRows = [
  ["状态管理", "状态切换", "状态切换时间", "需求 2.3", "已选"],
  ["按键交互", "长按操作", "长按功能触发", "需求 3.1", "已选"],
  ["指示灯", "红灯提示", "闪烁频率", "需求 4.2", "未选"],
  ["连接", "蓝牙配对", "配对失败提示", "需求 5.4", "未选"],
];

export function WorkflowPrototype() {
  const [activeTab, setActiveTab] = useState<TabId>("upload");
  const [mode, setMode] = useState<RunMode>("skill");
  const [lastAction, setLastAction] = useState("尚未执行真实操作");
  const [showProjectManager, setShowProjectManager] = useState(false);

  const chooseTab = (tab: TabId) => {
    setActiveTab(tab);
    setLastAction(`正在审阅“${tabs.find((item) => item.id === tab)?.label}”页面`);
  };

  const content = <PrototypePageContent activeTab={activeTab} mode={mode} setMode={setMode}
    onAction={setLastAction} />;
  return <main className="prototype-shell">
    <header className="prototype-header">
      <p>PROTOTYPE · 只用于确认前端信息架构，不调用后端或 AI</p>
      <h1>AI 测试用例生成平台</h1>
      <span>当前状态：页签「{tabs.find((item) => item.id === activeTab)?.label}」；模式「{modeLabel(mode)}」；{lastAction}</span>
    </header>
    <ProjectContextBar onOpenManager={() => setShowProjectManager(true)} onAction={setLastAction} />
    {showProjectManager && <ProjectManager onClose={() => setShowProjectManager(false)} onAction={setLastAction} />}
    <TabsFirstLayout activeTab={activeTab} chooseTab={chooseTab}>{content}</TabsFirstLayout>
  </main>;
}

function ProjectContextBar({ onOpenManager, onAction }: { onOpenManager: () => void; onAction: (message: string) => void }) {
  return <section className="prototype-project-bar"><div><small>当前测试设计项目</small><strong>智能手环 v0.1</strong><span>需求版本 V3 · 最近更新：今天 20:40 · 已选测试点：2</span></div><div><button type="button" onClick={onOpenManager}>项目管理</button><button type="button" onClick={() => onAction("已演示：下载智能手环 v0.1 的项目交付包")}>下载项目交付包</button><button type="button" onClick={() => onAction("已演示：打开本项目的资料、分析和用例历史")}>查看项目历史</button></div></section>;
}

function ProjectManager({ onClose, onAction }: { onClose: () => void; onAction: (message: string) => void }) {
  return <section className="prototype-project-manager" role="dialog" aria-modal="true" aria-label="项目管理原型"><header><div><p>项目管理</p><h2>选择或管理测试设计项目</h2><span>所有资料、需求版本、分析、测试范围、用例和下载记录均归属一个项目。</span></div><button type="button" onClick={onClose}>关闭</button></header><div className="prototype-project-actions"><input aria-label="搜索项目" placeholder="搜索项目名称、测试对象或版本" /><button type="button">新建测试设计项目</button></div><div className="prototype-project-list"><ProjectCard title="智能手环 v0.1" detail="需求版本 V3 · 已分析 126 条 · 已生成 42 条用例" action="打开当前项目" onAction={onAction} /><ProjectCard title="移动端登录改版" detail="需求版本 V2 · 已分析 38 条 · 上次导出：昨天" action="打开项目" onAction={onAction} /><ProjectCard title="设备升级流程" detail="需求版本 V1 · 未开始需求分析" action="打开项目" onAction={onAction} /></div></section>;
}

function ProjectCard({ title, detail, action, onAction }: { title: string; detail: string; action: string; onAction: (message: string) => void }) {
  return <article><div><strong>{title}</strong><span>{detail}</span><small>历史记录：资料 2 · 分析运行 4 · 用例生成 3 · 导出 2</small></div><div><button type="button" onClick={() => onAction(`已演示：${action}「${title}」`)}>{action}</button><button type="button" onClick={() => onAction(`已演示：下载「${title}」项目交付包`)}>下载交付包</button></div></article>;
}

function TabsFirstLayout({ activeTab, chooseTab, children }: LayoutProps) {
  return <section className="prototype-variant prototype-tabs-first">
    <header className="prototype-product-bar"><strong>AI 测试用例生成平台</strong><span>上传文档 → 需求分析 → 新增建议 → 审核 → 测试用例</span></header>
    <TabStrip activeTab={activeTab} chooseTab={chooseTab} />
    <div className="prototype-two-column"><aside className="prototype-context-card"><h2>当前项目</h2><p>智能手环 v0.1</p><hr /><p>已解析：1 份资料</p><p>已选测试点：2 项</p><p>当前结果：Skill 工作流</p><hr /><h2>模型接入</h2><p>硅基流动 · Qwen3.5-27B</p><p>本地已记住 Key · 已验证</p><button type="button">打开已有模型配置</button></aside><section>{children}</section></div>
  </section>;
}

type LayoutProps = { activeTab: TabId; chooseTab: (tab: TabId) => void; children: ReactNode };

function TabStrip({ activeTab, chooseTab }: Omit<LayoutProps, "children">) {
  return <nav className="prototype-tab-strip" aria-label="原型工作流页签"><TabButtons activeTab={activeTab} chooseTab={chooseTab} /></nav>;
}

function TabButtons({ activeTab, chooseTab }: Omit<LayoutProps, "children">) {
  return <>{tabs.map((tab, index) => <button key={tab.id} type="button" className={activeTab === tab.id ? "selected" : ""}
    onClick={() => chooseTab(tab.id)}><small>{index + 1}</small>{tab.label}</button>)}</>;
}

function PrototypePageContent({ activeTab, mode, setMode, onAction }: {
  activeTab: TabId; mode: RunMode; setMode: (mode: RunMode) => void; onAction: (message: string) => void;
}) {
  if (activeTab === "upload") return <section className="prototype-page-content"><PageTitle title="上传文档" subtitle="本页面不调用 AI。上传并解析后，直接查看文档解析结果。" />
    <label>补充说明（可选）<textarea placeholder="例如：请重点关注状态切换、按键操作和异常提示。" /></label>
    <div className="prototype-upload-row"><button type="button" onClick={() => onAction("已演示：上传并解析资料，不调用 AI")}>上传并解析</button><span>支持 Excel、PDF、Word、Markdown、文本</span></div>
    <section className="prototype-result-card"><header><h3>文档解析结果</h3><button type="button">下载解析结果</button></header><p>智能手环需求说明.pdf · 解析成功 · 12 个章节 · 3 张表格 · 166 个来源片段</p><details open><summary>查看结构预览</summary><p>3. 状态管理　4. 按键交互　5. 指示灯　6. 连接与异常处理</p></details></section>
  </section>;
  if (activeTab === "analysis") return <section className="prototype-page-content"><PageTitle title="需求分析" subtitle="AI 从上传资料与补充说明中识别功能点、测试项和测试点；勾选内容就是后续测试用例范围。" />
    <AIMode mode={mode} setMode={setMode} /><RunStatus status="尚未执行" detail="开始后将显示准备输入、调用模型、校验输出和保存结果。" />
    <div className="prototype-action-row"><button type="button" onClick={() => onAction(`已演示：以${modeLabel(mode)}开始需求分析`)}>开始需求分析</button><button type="button">下载需求分析表</button><span>已选 2 项，将作为测试用例范围</span></div><AnalysisFilters /><AnalysisTable /><Pagination summary="共 126 条；当前筛选命中 38 条；原型展示第 1 页样例" />
  </section>;
  if (activeTab === "suggestions") return <section className="prototype-page-content"><PageTitle title="新增建议" subtitle="由 AI 主动补充遗漏的功能、测试项和测试点；接纳后回流到需求分析表。" />
    <AIMode mode={mode} setMode={setMode} /><RunStatus status="已完成 · Skill 工作流" detail="耗时 37 秒；输入 1,240 Token；输出 896 Token；费用为估算值。" />
    <div className="prototype-action-row"><button type="button" onClick={() => onAction(`已演示：以${modeLabel(mode)}分析新增建议`)}>AI 分析新增建议</button><button type="button">下载新增建议</button></div>
    <SuggestionCard title="状态切换时间验证" relation="状态机 / 状态切换时间" /><SuggestionCard title="蓝牙配对失败后的指示灯状态" relation="连接 / 蓝牙配对 / 异常提示" />
  </section>;
  if (activeTab === "review") return <section className="prototype-page-content"><PageTitle title="审核" subtitle="可选的 AI 角色审核；不做审核也可以直接生成测试用例。" />
    <fieldset className="prototype-role-picker"><legend>选择审核身份</legend><label><input type="checkbox" /> 产品经理</label><label><input type="checkbox" /> 项目经理</label><label><input type="checkbox" defaultChecked /> 测试经理</label></fieldset><AIMode mode={mode} setMode={setMode} />
    <div className="prototype-action-row"><button type="button" onClick={() => onAction(`已演示：以${modeLabel(mode)}开始角色审核`)}>开始审核</button><button type="button">跳过审核，进入测试用例</button><button type="button">下载审核报告</button></div><RunStatus status="尚未执行" detail="选择一个或多个身份后，可获得风险、遗漏与可测试性建议。" />
  </section>;
  return <section className="prototype-page-content"><PageTitle title="测试用例" subtitle="模板、模式、生成、预览、编辑和下载全部在本页完成。" />
    <fieldset className="prototype-template-picker"><legend>1. 测试用例模板</legend><label><input type="radio" name="template" defaultChecked /> 使用默认测试用例模板</label><label><input type="radio" name="template" /> 上传测试用例模板</label><button type="button">查看模板字段</button></fieldset>
    <section className="prototype-scope-summary"><strong>2. 当前测试范围</strong><span>已选 2 个测试点：状态切换时间、长按功能触发</span></section><section><strong>3. 生成模式</strong><AIMode mode={mode} setMode={setMode} /></section><label>4. 补充生成要求（可选）<textarea placeholder="例如：优先输出 P0/P1；每个边界场景独立成用例。" /></label>
    <div className="prototype-action-row"><button type="button" onClick={() => onAction(`已演示：以${modeLabel(mode)}生成测试用例`)}>生成测试用例</button><button type="button">导出 Excel</button><button type="button">导出 JSON</button></div><RunStatus status="未生成" detail="生成后将在本页显示候选用例表、可编辑详情与质量提示。" /><CaseHistoryAndTable />
  </section>;
}

function PageTitle({ title, subtitle }: { title: string; subtitle: string }) { return <header className="prototype-page-title"><div><p>工作页</p><h2>{title}</h2><span>{subtitle}</span></div><span className="prototype-badge">演示数据</span></header>; }

function AIMode({ mode, setMode }: { mode: RunMode; setMode: (mode: RunMode) => void }) { return <fieldset className="prototype-mode-picker"><legend>运行方式</legend>{(["direct", "skill", "local"] as RunMode[]).map((item) => <label key={item}><input type="radio" name="prototype-mode" checked={mode === item} onChange={() => setMode(item)} /> {modeLabel(item)}</label>)}</fieldset>; }

function RunStatus({ status, detail }: { status: string; detail: string }) { return <section className="prototype-run-status"><strong>运行状态：{status}</strong><span>{detail}</span></section>; }

function AnalysisTable() { return <div className="prototype-table-wrap"><table><thead><tr><th>纳入范围</th><th>功能模块</th><th>测试项</th><th>测试点</th><th>来源</th><th>状态</th></tr></thead><tbody>{analysisRows.map((row, index) => <tr key={row[2]}><td><input type="checkbox" defaultChecked={index < 2} aria-label={`选择-${row[2]}`} /></td>{row.map((value) => <td key={value}>{value}</td>)}</tr>)}</tbody></table></div>; }

function AnalysisFilters() { return <section className="prototype-filter-bar" aria-label="需求分析筛选"><label>搜索<input placeholder="功能点、测试项或测试点" /></label><label>功能模块<select defaultValue="all"><option value="all">全部模块</option><option>状态管理</option><option>按键交互</option></select></label><label>测试项<select defaultValue="all"><option value="all">全部测试项</option><option>状态切换</option><option>长按操作</option></select></label><label>勾选状态<select defaultValue="all"><option value="all">全部</option><option>已选</option><option>未选</option></select></label><button type="button">清除筛选</button><button type="button">全选本页</button></section>; }

function Pagination({ summary }: { summary: string }) { return <footer className="prototype-pagination"><span>{summary}</span><label>每页<select defaultValue="20"><option>20</option><option>50</option><option>100</option></select> 条</label><button type="button">上一页</button><strong>第 1 / 2 页</strong><button type="button">下一页</button></footer>; }

function CaseHistoryAndTable() { return <section className="prototype-case-history"><header><div><strong>候选测试用例</strong><span>可切换本次生成与历史记录；筛选、分页和选择状态均独立保存。</span></div><label>查看<select defaultValue="current"><option value="current">本次生成（42 条）</option><option>2026-10-09 Skill 工作流（29 条）</option><option>2026-10-06 直接调用（18 条）</option></select></label></header><section className="prototype-filter-bar"><label>搜索<input placeholder="用例标题或测试点" /></label><label>功能模块<select defaultValue="all"><option value="all">全部模块</option><option>状态管理</option><option>按键交互</option></select></label><label>优先级<select defaultValue="all"><option value="all">全部优先级</option><option>P0</option><option>P1</option></select></label><label>纳入状态<select defaultValue="all"><option value="all">全部</option><option>已纳入</option><option>未纳入</option></select></label></section><div className="prototype-table-wrap"><table><thead><tr><th>纳入</th><th>用例标题</th><th>测试点</th><th>优先级</th><th>生成记录</th></tr></thead><tbody><tr><td><input type="checkbox" defaultChecked /></td><td>状态切换应在规定时间内完成</td><td>状态切换时间</td><td>P1</td><td>本次 · Skill 工作流</td></tr><tr><td><input type="checkbox" /></td><td>长按操作应触发对应功能</td><td>长按功能触发</td><td>P1</td><td>本次 · Skill 工作流</td></tr></tbody></table></div><Pagination summary="共 42 条；当前筛选命中 42 条；原型展示第 1 页样例" /></section>; }

function SuggestionCard({ title, relation }: { title: string; relation: string }) { return <article className="prototype-suggestion-card"><header><label><input type="checkbox" defaultChecked /> 接纳新增测试点</label><span>中优先级</span></header><strong>建议增加：{title}</strong><p>关联：{relation}</p><small>AI 理由：现有需求包含相关功能描述，但缺少该异常或边界验证方向。</small></article>; }

function modeLabel(mode: RunMode): string { return ({ direct: "真实模型（直接调用）", skill: "真实模型（Skill 工作流）", local: "本地模式（不调用 AI）" })[mode]; }
