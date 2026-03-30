export type DocStatus = "draft" | "approved" | "delisted";
export type ObjectType = "table" | "view" | "dashboard" | "stored_procedure";

export interface ObjectTypeInfo {
  value: string;
  label: string;
  display_name: string;
  icon: string;
}

export interface DocField {
  name: string;
  type: string;
  description: string;
  nullable: boolean;
}

export interface DocContent {
  name?: string;
  object_type?: string;
  business_domain?: string;
  description?: string;
  owner?: string;
  last_updated?: string;
  data_source?: string;
  fields?: DocField[];
  refresh_frequency?: string;
  metrics?: string[];
  dependencies?: string[];
  transformation_logic?: string;
  sql_definition?: string;
  referenced_tables?: Array<{ name: string }>;
}

export interface Document {
  id: string;
  name: string;
  object_type: ObjectType;
  status: DocStatus;
  content: DocContent;
  created_by: string;
  created_at: string;
  updated_at: string;
  last_audit_issues?: AuditIssue[] | null;
}

export interface AuditIssue {
  field: string;
  issue: string;
  suggestion?: string;
}

export interface AuditResult {
  result: "approved" | "observations";
  issues: AuditIssue[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface PendingPanel {
  doc_id: string;
  mode: "viewer" | "editor";
}

export interface ItemFieldDef {
  name: string;
  type: string;
}

export interface FieldDef {
  path: string;
  required: boolean;
  completion: string;
  field_type: string;
  is_array: boolean;
  valid_values?: string[];
  min_words?: number;
  item_fields?: ItemFieldDef[];
  user_help?: string;
}

export interface SectionDef {
  key: string;
  label: string;
  fields: FieldDef[];
}

export interface DocSpec {
  object_type: string;
  sections: SectionDef[];
  enums: Record<string, string[]>;
}
