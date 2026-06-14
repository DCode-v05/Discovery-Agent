// Mirrors the backend Pydantic schemas (the API returns these shapes).

export interface Evidence {
  quote: string;
  source_doc: string;
  location: string;
  grounded: boolean;
}

export interface System {
  name: string;
  category: string;
  auth_method: string;
  key_entities: string[];
  business_processes: string[];
  criticality: string;
  confidence: number;
  confidence_tier: string;
  uncertainty_note: string | null;
  needs_review: boolean;
  evidence: Evidence[];
  source_docs: string[];
}

export interface SkippedDocument {
  document: string;
  reason: string;
  needs: string;
}

export interface Inventory {
  run_id: string;
  generated_at: string;
  document_count: number;
  systems_count: number;
  systems: System[];
  warnings: string[];
  skipped_documents: SkippedDocument[];
}

export interface DiscoveryResponse {
  run_id: string;
  inventory: Inventory;
  markdown: string;
}

export interface DataFlow {
  source_system: string;
  destination_system: string;
  entity: string;
  trigger: string;
}

export interface UseCaseMapping {
  use_case_id: string;
  name: string;
  required_systems: string[];
  missing_systems: string[];
  data_flows: DataFlow[];
  rationale: string;
}

export interface IntegrationGap {
  id: string;
  source_system: string;
  destination_system: string;
  integration_name: string;
  description: string;
  status: string;
  effort_level: string;
  effort_days: number;
  required_by_use_cases: string[];
  blocks_use_cases: string[];
  business_impact_score: number;
  priority: string;
  dependency_note: string;
}

export interface GapReport {
  run_id: string;
  generated_at: string;
  use_case_count: number;
  gap_count: number;
  mappings: UseCaseMapping[];
  gaps: IntegrationGap[];
  dependency_statements: string[];
  summary: string;
  warnings: string[];
}

export interface GapResponse {
  run_id: string;
  report: GapReport;
  markdown: string;
}

export interface ValidationResult {
  syntax_ok: boolean;
  import_ok: boolean;
  yaml_ok: boolean;
  tests_pass: boolean | null;
  issues: string[];
}

export interface GeneratedFile {
  path: string;
  content: string;
  language: string;
}

export interface ConnectorArtifact {
  gap_id: string;
  system_name: string;
  integration_name: string;
  package_name: string;
  files: GeneratedFile[];
  validation: ValidationResult;
  notes: string;
  error: string | null;
}

export interface CodegenResult {
  run_id: string;
  generated_at: string;
  artifact_count: number;
  artifacts: ConnectorArtifact[];
  bundle_path: string | null;
  warnings: string[];
}

export interface CodegenResponse {
  run_id: string;
  result: CodegenResult;
  markdown: string;
  bundle_url: string | null;
}

export interface Health {
  status: string;
  providers: { gemini: boolean; groq: boolean };
  models: Record<string, string>;
  routes: Record<string, string>;
}

export interface RunEvent {
  run_id: string;
  ts: number;
  event: string;
  level: string;
  [key: string]: unknown;
}

export interface Ledger {
  run_id: string;
  kind: string;
  events: RunEvent[];
}
