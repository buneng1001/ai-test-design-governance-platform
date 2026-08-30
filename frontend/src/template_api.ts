// 用例模板领域请求。
import { request } from "./api_client";
import type { TemplateMappingVersion, TemplateSheet } from "./api_types";

const toTemplateMapping = (sheet: TemplateSheet) => ({
  sheet_name: sheet.name, role: sheet.role, participates: sheet.participates,
  title_row: sheet.title_row, field_mapping: sheet.field_mapping,
});
export const uploadTemplate = (projectId: number, filename: string,
  contentBase64: string): Promise<TemplateMappingVersion> =>
  request(`/api/projects/${projectId}/template-mappings`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, content_base64: contentBase64 }),
  });
export const confirmTemplate = (projectId: number, mappingId: number, confirmerName: string,
  mappings: TemplateSheet[]): Promise<TemplateMappingVersion> =>
  request(`/api/projects/${projectId}/template-mappings/${mappingId}/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmer_name: confirmerName, mappings: mappings.map(toTemplateMapping) }),
  });
export const validateTemplate = (projectId: number, mappingId: number, confirmerName: string,
  mappings: TemplateSheet[]): Promise<{ valid: boolean; diagnostics: TemplateSheet["diagnostics"] }> =>
  request(`/api/projects/${projectId}/template-mappings/${mappingId}/validate`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmer_name: confirmerName, mappings: mappings.map(toTemplateMapping) }),
  });
