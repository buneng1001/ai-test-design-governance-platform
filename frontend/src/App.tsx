import { FormEvent, useEffect, useState } from "react";

import { createProject, deleteProject, getProject, listProjects, Project, ProjectInput, updateProject } from "./api";
import { AssetProvenancePanel } from "./AssetProvenancePanel";
import { AIRunPanel } from "./AIRunPanel";
import { RequirementImportPanel } from "./RequirementImportPanel";
import { RequirementReviewPanel } from "./RequirementReviewPanel";
import { TestDesignPanel } from "./TestDesignPanel";
import { TemplateMappingPanel } from "./TemplateMappingPanel";
import { TaskPublicationPanel } from "./TaskPublicationPanel";
import { ExecutionBatchPanel } from "./ExecutionBatchPanel";
import { ExecutionResultPanel } from "./ExecutionResultPanel";
import { CoveragePanel } from "./CoveragePanel";
import { ChangeImpactPanel } from "./ChangeImpactPanel";
import { CaseGenerationPanel } from "./CaseGenerationPanel";
import { ReportsPanel } from "./ReportsPanel";
import { ModelConfigPanel } from "./ModelConfigPanel";
import "./styles.css";

const emptyProject: ProjectInput = {
  name: "",
  test_object: "",
  software_version: "",
  description: "",
  settings: { requirement_language: "zh-CN" },
};

export function App() {
  const [initialProjectId] = useState(() => parseProjectId(window.location.pathname));
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [projectInput, setProjectInput] = useState<ProjectInput>(emptyProject);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [error, setError] = useState("");
  const [saveStatus, setSaveStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [versionRefreshKey, setVersionRefreshKey] = useState(0);
  const [newlyPublishedVersionId, setNewlyPublishedVersionId] = useState<number | null>(null);
  const [assetsRefreshKey, setAssetsRefreshKey] = useState(0);

  useEffect(() => {
    const loadInitialView = async () => {
      try {
        const result = initialProjectId ? await getProject(initialProjectId) : await listProjects();
        if (Array.isArray(result)) {
          setProjects(result);
        } else {
          setActiveProject(result);
          setProjectInput(toInput(result));
        }
      } catch (reason) {
        setError(errorMessage(reason));
      } finally {
        setLoading(false);
      }
    };
    void loadInitialView();
  }, [initialProjectId]);

  const openProject = (project: Project) => {
    window.history.pushState({}, "", `/projects/${project.id}`);
    setActiveProject(project);
    setProjectInput(toInput(project));
    setError("");
  };

  const submitCreate = async (event: FormEvent) => {
    event.preventDefault();
    if (!validate(projectInput, setError)) return;
    try {
      openProject(await createProject(projectInput));
    } catch (reason) {
      setError(errorMessage(reason));
    }
  };

  const submitUpdate = async (event: FormEvent) => {
    event.preventDefault();
    if (!activeProject || !validate(projectInput, setError)) return;
    try {
      const updated = await updateProject(activeProject.id, projectInput);
      setActiveProject(updated);
      setProjectInput(toInput(updated));
      setError("");
      setSaveStatus(`✓ 已保存 · ${new Date().toLocaleTimeString()}`);
    } catch (reason) {
      setError(errorMessage(reason));
    }
  };

  if (loading) return <main className="shell"><p>正在加载测试设计项目…</p></main>;

  if (activeProject) {
    return (
      <main className="shell">
        <button className="link-button" onClick={() => window.location.assign("/")}>← 返回项目列表</button>
        <p className="eyebrow">项目工作台</p>
        <h1>{activeProject.name}</h1>
        <p className="object-name">测试对象：{activeProject.test_object}</p>
        <p className="object-name">软件版本：{activeProject.software_version}</p>
        <div className="workspace-layout">
          <WorkspaceNavigation />
          <div className="workspace-content">
          <section className="panel" id="project-info">
          <h2 id="project-info-title">项目信息</h2>
          <ProjectForm input={projectInput} setInput={setProjectInput} submitLabel="保存修改" onSubmit={submitUpdate} />
          <button type="button" className="danger-button" onClick={async () => {
            if (!window.confirm(`确定删除项目“${activeProject.name}”及其全部数据吗？此操作不可恢复。`)) return;
            try {
              await deleteProject(activeProject.id);
              window.location.assign("/");
            } catch (reason) {
              setError(errorMessage(reason));
            }
          }}>删除项目及全部数据</button>
          {error && <p role="alert" className="error">{error}</p>}
          {saveStatus && <p role="status" className="success">{saveStatus}</p>}
          </section>
        <AssetProvenancePanel projectId={activeProject.id} onAssetRegistered={() => {
          setAssetsRefreshKey((current) => current + 1);
        }} />
        <ModelConfigPanel />
        <AIRunPanel projectId={activeProject.id} />
        <RequirementImportPanel projectId={activeProject.id} assetsRefreshKey={assetsRefreshKey}
          onVersionPublished={(versionId) => {
          setNewlyPublishedVersionId(versionId);
          setVersionRefreshKey((current) => current + 1);
        }} />
        <p className="muted">发布需求版本后，可在下方选择 V1、V2 等版本进入需求确认。</p>
        <RequirementReviewPanel projectId={activeProject.id} versionRefreshKey={versionRefreshKey}
          newlyPublishedVersionId={newlyPublishedVersionId} />
        <TestDesignPanel projectId={activeProject.id} />
        <TemplateMappingPanel projectId={activeProject.id} />
        <CaseGenerationPanel projectId={activeProject.id} />
        <TaskPublicationPanel projectId={activeProject.id} />
        <ExecutionBatchPanel projectId={activeProject.id} />
        <ExecutionResultPanel projectId={activeProject.id} />
        <CoveragePanel projectId={activeProject.id} />
        <ChangeImpactPanel projectId={activeProject.id} />
        <ReportsPanel projectId={activeProject.id} />
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">AI 测试设计与治理平台</p>
          <h1>测试设计项目</h1>
          <p>围绕测试对象管理需求资料与后续测试设计资产。</p>
        </div>
        {!showCreateForm && (
          <button onClick={() => { setShowCreateForm(true); setProjectInput(emptyProject); }}>
            创建测试设计项目
          </button>
        )}
      </header>
      {showCreateForm && (
        <section className="panel">
          <h2>创建测试设计项目</h2>
          <ProjectForm
            input={projectInput}
            setInput={setProjectInput}
            submitLabel="创建并进入工作台"
            onSubmit={submitCreate}
          />
          {error && <p role="alert" className="error">{error}</p>}
        </section>
      )}
      {!showCreateForm && projects.length === 0 && (
        <section className="empty-state">
          <h2>还没有测试设计项目</h2>
          <p>创建第一个项目，明确测试对象和项目边界。</p>
        </section>
      )}
      <section className="project-grid" aria-label="测试设计项目列表">
        {projects.map((project) => (
          <button className="project-card" key={project.id} onClick={() => openProject(project)}>
            <strong>{project.name}</strong>
            <span>{project.test_object}</span>
          </button>
        ))}
      </section>
    </main>
  );
}

const navigationItems = [
  { id: "project-info", label: "项目信息" },
  { id: "asset-provenance", label: "资产来源记录" },
  { id: "model-config", label: "模型配置" },
  {
    id: "requirement-import",
    label: "导入需求资料",
    children: [{ id: "requirement-package-list", label: "发布前资料包清单" }],
  },
  {
    id: "requirement-review",
    label: "需求评审与确认",
    children: [
      { id: "grouped-requirements", label: "按模块归并的需求表" },
      { id: "requirement-conflicts", label: "需求冲突表" },
      { id: "atomic-requirements", label: "原子需求候选" },
      { id: "review-findings", label: "需求评审发现" },
    ],
  },
  { id: "test-design", label: "测试维度、范围、风险与自动化" },
  { id: "case-generation", label: "生成可追踪的候选测试用例" },
  { id: "template-mapping", label: "用例模板映射" },
  { id: "case-review", label: "三角色 AI 评审与用例确认" },
  { id: "task-publication", label: "发布测试任务" },
  { id: "execution-batch", label: "创建执行批次" },
  { id: "execution-results", label: "导入运行结果" },
  { id: "coverage", label: "治理指标与缺口" },
  { id: "change-impact", label: "变更影响与回归治理" },
  { id: "reports-title", label: "报告与审计包" },
  { id: "ai-run-audit", label: "AI 运行审计" },
] as const;

function WorkspaceNavigation() {
  return (
    <nav className="workspace-navigation" aria-label="项目工作台导航">
      <p className="workspace-navigation-title">项目导航</p>
      <ul>
        {navigationItems.map((item) => (
          <li key={item.id}>
            <a href={`#${item.id}`}>{item.label}</a>
            {"children" in item && <ul>
              {item.children.map((child) => <li key={child.id}><a href={`#${child.id}`}>{child.label}</a></li>)}
            </ul>}
          </li>
        ))}
      </ul>
    </nav>
  );
}

interface ProjectFormProps {
  input: ProjectInput;
  setInput: (input: ProjectInput) => void;
  submitLabel: string;
  onSubmit: (event: FormEvent) => void;
}

function ProjectForm({ input, setInput, submitLabel, onSubmit }: ProjectFormProps) {
  const setField = (field: keyof Omit<ProjectInput, "settings">, value: string) => {
    setInput({ ...input, [field]: value });
  };
  return (
    <form onSubmit={onSubmit} className="project-form">
      <label>
        项目名称
        <span><i className="required-mark">*</i><input aria-label="项目名称" value={input.name} maxLength={100}
          required onChange={(event) => setField("name", event.target.value)} /></span>
      </label>
      <label>
        测试对象
        <span><i className="required-mark">*</i><input aria-label="测试对象"
          value={input.test_object}
          maxLength={200}
          required
          onChange={(event) => setField("test_object", event.target.value)}
        /></span>
      </label>
      <label>
        软件版本
        <span><i className="required-mark">*</i><input aria-label="软件版本" value={input.software_version}
          maxLength={100} required
          onChange={(event) => setField("software_version", event.target.value)} /></span>
      </label>
      <label>
        项目描述
        <textarea
          value={input.description}
          maxLength={2000}
          onChange={(event) => setField("description", event.target.value)}
        />
      </label>
      <label>
        需求资料默认语言
        <select value={input.settings.requirement_language} onChange={(event) => setInput({
          ...input,
          settings: { requirement_language: event.target.value as "zh-CN" | "en-US" },
        })}>
          <option value="zh-CN">简体中文</option>
          <option value="en-US">English</option>
        </select>
      </label>
      <button type="submit">{submitLabel}</button>
    </form>
  );
}

const parseProjectId = (path: string): number | null => {
  const match = path.match(/^\/projects\/(\d+)$/);
  return match ? Number(match[1]) : null;
};

const toInput = ({ name, test_object, software_version, description, settings }: Project): ProjectInput => ({
  name,
  test_object,
  software_version,
  description,
  settings,
});

const validate = (input: ProjectInput, setError: (message: string) => void): boolean => {
  if (!input.name.trim() || !input.test_object.trim() || !input.software_version.trim()) {
    setError("请填写项目名称、测试对象和软件版本");
    return false;
  }
  setError("");
  return true;
};

const errorMessage = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
