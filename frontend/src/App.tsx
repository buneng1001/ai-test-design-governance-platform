import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { createProject, getProject, Project, ProjectInput, updateProject } from "./api";
import { WorkflowPrototype } from "./WorkflowPrototype";
import { WorkflowShell } from "./WorkflowShell";
import { downloadDeliveryPackage, listProjectSummaries, setProjectArchived } from "./v020_api";
import type { ProjectSummary } from "./v020_types";
import "./styles.css";

const emptyProject: ProjectInput = { name: "", test_object: "", software_version: "", description: "",
  settings: { requirement_language: "zh-CN" } };

export function App() {
  if (window.location.pathname === "/prototype/v0-2-workflow") return <WorkflowPrototype />;
  return <ProjectApp />;
}

function ProjectApp() {
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectInput, setProjectInput] = useState<ProjectInput>(emptyProject);
  const [showCreate, setShowCreate] = useState(false); const [showArchived, setShowArchived] = useState(false);
  const [search, setSearch] = useState(""); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  const initialProjectId = useMemo(() => parseProjectId(window.location.pathname), []);
  const loadProjects = useCallback(async (archived = false) => {
    setProjects(await listProjectSummaries(archived));
  }, []);
  useEffect(() => { void (async () => { try {
    if (initialProjectId) { const project = await getProject(initialProjectId); setActiveProject(project); setProjectInput(toInput(project)); }
    else await loadProjects(false);
  } catch (reason) { setError(message(reason)); } finally { setLoading(false); } })(); }, [initialProjectId, loadProjects]);
  const openProject = async (projectId: number) => { try { const project = await getProject(projectId); setActiveProject(project);
    setProjectInput(toInput(project)); window.history.pushState({}, "", `/projects/${project.id}`); setError(""); }
  catch (reason) { setError(message(reason)); } };
  const openManager = async () => { window.history.pushState({}, "", "/"); setActiveProject(null); setShowArchived(false);
    setLoading(true); try { await loadProjects(false); } catch (reason) { setError(message(reason)); } finally { setLoading(false); } };
  const submitCreate = async (event: FormEvent) => { event.preventDefault(); if (!validate(projectInput, setError)) return;
    try { const project = await createProject(projectInput); await openProject(project.id); } catch (reason) { setError(message(reason)); } };
  const submitUpdate = async (event: FormEvent) => { event.preventDefault(); if (!activeProject || !validate(projectInput, setError)) return;
    try { const project = await updateProject(activeProject.id, projectInput); setActiveProject(project); setProjectInput(toInput(project)); }
    catch (reason) { setError(message(reason)); } };
  const toggleArchiveView = async (archived: boolean) => { setShowArchived(archived); try { setProjects(await listProjectSummaries(archived)); }
    catch (reason) { setError(message(reason)); } };
  const filtered = projects.filter((project) => [project.name, project.test_object, project.software_version]
    .some((value) => value.toLowerCase().includes(search.trim().toLowerCase())));
  if (loading) return <main className="shell"><p>正在加载测试设计项目…</p></main>;
  if (activeProject) return <main className="product-shell"><WorkflowShell projectId={activeProject.id} projectName={activeProject.name}
    testObject={activeProject.test_object} softwareVersion={activeProject.software_version} onOpenProjects={() => void openManager()} />
    <details className="project-settings"><summary>项目设置</summary><ProjectForm input={projectInput} setInput={setProjectInput} submitLabel="保存项目设置" onSubmit={submitUpdate} /></details>
    {error && <p role="alert" className="error floating-error">{error}</p>}</main>;
  return <main className="project-manager-shell"><header className="manager-header"><div><p className="eyebrow">AI 测试用例生成平台</p>
    <h1>测试设计项目</h1><p>选择项目后进入“上传文档 → 需求分析 → 新增建议 → 审核 → 测试用例”。</p></div>
    <button type="button" onClick={() => { setShowCreate(true); setProjectInput(emptyProject); }}>新建测试设计项目</button></header>
    <section className="manager-toolbar"><input aria-label="搜索项目" value={search} placeholder="搜索项目名称、测试对象或版本" onChange={(e) => setSearch(e.target.value)} />
      <div><button type="button" className={!showArchived ? "selected secondary" : "secondary"} onClick={() => void toggleArchiveView(false)}>进行中的项目</button>
        <button type="button" className={showArchived ? "selected secondary" : "secondary"} onClick={() => void toggleArchiveView(true)}>已归档</button></div></section>
    {showCreate && <section className="panel create-project-panel"><header><h2>创建测试设计项目</h2><button type="button" className="secondary" onClick={() => setShowCreate(false)}>取消</button></header>
      <ProjectForm input={projectInput} setInput={setProjectInput} submitLabel="创建并进入工作台" onSubmit={submitCreate} /></section>}
    <section className="formal-project-grid" aria-label="测试设计项目列表">{filtered.map((project) => <article className="formal-project-card" key={project.id}>
      <button type="button" className="project-open" onClick={() => void openProject(project.id)}><strong>{project.name}</strong>
        <span>{project.test_object} · {project.software_version}</span><small>最近更新：{new Date(project.updated_at).toLocaleString()}</small>
        <small>需求版本：{project.current_requirement_version ?? "未建立"} · 分析：{project.latest_analysis_status} · 用例：{project.latest_case_status}</small>
        <small>最近导出：{project.latest_export_at ? new Date(project.latest_export_at).toLocaleString() : "无"}</small></button>
      <div><button type="button" className="secondary" onClick={() => void downloadDeliveryPackage(project.id).catch((reason) => setError(message(reason)))}>下载交付包</button>
        <button type="button" className="secondary" onClick={() => void setProjectArchived(project.id, !showArchived).then(() => loadProjects(showArchived))}>{showArchived ? "恢复项目" : "归档项目"}</button></div>
    </article>)}</section>
    {!filtered.length && <section className="empty-state"><h2>{showArchived ? "没有已归档项目" : "还没有测试设计项目"}</h2><p>新建项目后，资料、分析范围、用例和历史记录都会按项目保存。</p></section>}
    {error && <p role="alert" className="error">{error}</p>}
  </main>;
}

function ProjectForm({ input, setInput, submitLabel, onSubmit }: { input: ProjectInput; setInput: (value: ProjectInput) => void;
  submitLabel: string; onSubmit: (event: FormEvent) => void }) {
  const setField = (field: keyof Omit<ProjectInput, "settings">, value: string) => setInput({ ...input, [field]: value });
  return <form onSubmit={onSubmit} className="project-form"><label>项目名称<span><i className="required-mark">*</i><input aria-label="项目名称" value={input.name} required maxLength={100} onChange={(e) => setField("name", e.target.value)} /></span></label>
    <label>测试对象<span><i className="required-mark">*</i><input aria-label="测试对象" value={input.test_object} required maxLength={200} onChange={(e) => setField("test_object", e.target.value)} /></span></label>
    <label>软件版本<span><i className="required-mark">*</i><input aria-label="软件版本" value={input.software_version} required maxLength={100} onChange={(e) => setField("software_version", e.target.value)} /></span></label>
    <label>项目描述<textarea aria-label="项目描述" value={input.description} maxLength={2000} onChange={(e) => setField("description", e.target.value)} /></label>
    <label>需求资料默认语言<select value={input.settings.requirement_language} onChange={(e) => setInput({ ...input, settings: { requirement_language: e.target.value as "zh-CN" | "en-US" } })}><option value="zh-CN">简体中文</option><option value="en-US">English</option></select></label>
    <button type="submit">{submitLabel}</button></form>;
}
const parseProjectId = (path: string): number | null => { const match = path.match(/^\/projects\/(\d+)$/); return match ? Number(match[1]) : null; };
const toInput = ({ name, test_object, software_version, description, settings }: Project): ProjectInput => ({ name, test_object, software_version, description, settings });
const validate = (input: ProjectInput, setError: (value: string) => void) => { if (!input.name.trim() || !input.test_object.trim() || !input.software_version.trim()) { setError("请填写项目名称、测试对象和软件版本"); return false; } setError(""); return true; };
const message = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
