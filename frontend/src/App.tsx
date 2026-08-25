import { FormEvent, useEffect, useState } from "react";

import { createProject, getProject, listProjects, Project, ProjectInput, updateProject } from "./api";
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
import "./styles.css";

const emptyProject: ProjectInput = {
  name: "",
  test_object: "",
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
  const [loading, setLoading] = useState(true);

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
        <section className="panel">
          <h2>项目信息</h2>
          <ProjectForm input={projectInput} setInput={setProjectInput} submitLabel="保存修改" onSubmit={submitUpdate} />
          {error && <p role="alert" className="error">{error}</p>}
        </section>
        <AssetProvenancePanel projectId={activeProject.id} />
        <AIRunPanel projectId={activeProject.id} />
        <RequirementImportPanel projectId={activeProject.id} />
        <p className="muted">发布需求版本后，可在下方输入版本编号进入需求确认。</p>
        <RequirementReviewPanel projectId={activeProject.id} />
        <TestDesignPanel projectId={activeProject.id} />
        <TemplateMappingPanel projectId={activeProject.id} />
        <CaseGenerationPanel projectId={activeProject.id} />
        <TaskPublicationPanel projectId={activeProject.id} />
        <ExecutionBatchPanel projectId={activeProject.id} />
        <ExecutionResultPanel projectId={activeProject.id} />
        <CoveragePanel projectId={activeProject.id} />
        <ChangeImpactPanel projectId={activeProject.id} />
        <ReportsPanel projectId={activeProject.id} />
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
        <input value={input.name} maxLength={100} onChange={(event) => setField("name", event.target.value)} />
      </label>
      <label>
        测试对象
        <input
          value={input.test_object}
          maxLength={200}
          onChange={(event) => setField("test_object", event.target.value)}
        />
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

const toInput = ({ name, test_object, description, settings }: Project): ProjectInput => ({
  name,
  test_object,
  description,
  settings,
});

const validate = (input: ProjectInput, setError: (message: string) => void): boolean => {
  if (!input.name.trim() || !input.test_object.trim()) {
    setError("请填写项目名称和测试对象");
    return false;
  }
  setError("");
  return true;
};

const errorMessage = (reason: unknown): string => reason instanceof Error ? reason.message : "请求未完成";
