// 集中维护 HTTP 请求、会话请求头和统一错误解析逻辑。
interface ValidationError {
  loc?: unknown[];
  type?: string;
}

const fieldLabels: Record<string, string> = {
  name: "项目名称",
  test_object: "测试对象",
  description: "项目描述",
  requirement_language: "需求资料默认语言",
};

function formatErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return "请求未完成，请检查填写内容";
  return detail.map((error: ValidationError) => {
    const field = String(error.loc?.at(-1) ?? "项目字段");
    const label = fieldLabels[field] ?? field;
    if (error.type === "string_too_long") return `${label}超过长度限制`;
    if (error.type === "missing") return `${label}为必填项`;
    return `${label}填写不正确`;
  }).join("；");
}

export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(formatErrorDetail(body?.detail));
  }
  return response.json() as Promise<T>;
}

const sessionId = (): string => {
  const key = "ai-test-design-session-id";
  const existing = sessionStorage.getItem(key);
  if (existing) return existing;
  const created = crypto.randomUUID();
  sessionStorage.setItem(key, created);
  return created;
};

export const sessionHeaders = (): HeadersInit => ({ "X-Session-ID": sessionId() });

export const downloadResponseFile = async (response: Response, fallbackName: string): Promise<void> => {
  if (!response.ok) throw new Error(await response.text());
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = response.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] ?? fallbackName;
  link.click();
  URL.revokeObjectURL(url);
};
