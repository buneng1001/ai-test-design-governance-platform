// 集中维护 HTTP 请求、会话请求头和统一错误解析逻辑。
interface ValidationError {
  loc?: unknown[];
  type?: string;
  msg?: string;
  message?: string;
  detail?: unknown;
}

const fieldLabels: Record<string, string> = {
  name: "项目名称",
  test_object: "测试对象",
  description: "项目描述",
  requirement_language: "需求资料默认语言",
  body: "请求数据",
};

function formatErrorDetail(detail: unknown, fallback = "请求失败，请查看服务端诊断信息"): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const error = detail as ValidationError;
    if (typeof error.message === "string") return error.message;
    if (typeof error.msg === "string") return error.msg;
    if (error.detail !== undefined) return formatErrorDetail(error.detail);
    const code = typeof (detail as { code?: unknown }).code === "string"
      ? (detail as { code: string }).code
      : "";
    return code ? `请求失败（${code}），请查看服务端诊断信息` : "请求失败，请查看服务端诊断信息";
  }
  if (!Array.isArray(detail)) return fallback;
  if (detail.every((item) => typeof item === "string")) {
    return `AI 输出字段校验失败：${detail.slice(0, 3).join("；")}`;
  }
  return detail.map((error: ValidationError) => {
    const field = String(error.loc?.at(-1) ?? "项目字段");
    const label = fieldLabels[field] ?? field;
    if (error.type === "string_too_long") return `${label}超过长度限制`;
    if (error.type === "missing") return `${label}为必填项`;
    return field === "body" ? "请求数据格式不正确，请检查分析方式后重试" : `${label}填写不正确`;
  }).join("；");
}

export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const responseText = await response.text();
    let body: unknown = null;
    try {
      body = responseText ? JSON.parse(responseText) : null;
    } catch {
      body = responseText;
    }
    const detail = body && typeof body === "object" && !Array.isArray(body) && "detail" in body
      ? (body as { detail: unknown }).detail
      : body;
    const fallback = `请求失败（HTTP ${response.status}）：${response.statusText || "服务端未返回具体原因"}`;
    throw new Error(formatErrorDetail(detail, fallback));
  }
  return response.json() as Promise<T>;
}

const sessionId = (): string => {
  const key = "ai-test-design-session-id";
  const existing = localStorage.getItem(key);
  if (existing) return existing;
  const created = crypto.randomUUID();
  localStorage.setItem(key, created);
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
