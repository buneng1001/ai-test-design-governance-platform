// 项目领域的 API 类型。
export interface ProjectSettings {
  requirement_language: "zh-CN" | "en-US";
}

export interface ProjectInput {
  name: string;
  test_object: string;
  software_version: string;
  description: string;
  settings: ProjectSettings;
}

export interface Project extends ProjectInput {
  id: number;
  created_at: string;
  updated_at: string;
}
