export type CodeLanguage =
  | "bash"
  | "powershell"
  | "cmd"
  | "json"
  | "dotenv"
  | "yaml"
  | "text"
  | "python"
  | "typescript";

export type CalloutTone = "info" | "warn" | "danger";

export interface CodeBlockData {
  type: "code";
  language: CodeLanguage;
  code: string;
  label?: string;
}

export interface TableData {
  type: "table";
  head: string[];
  rows: string[][];
  caption?: string;
}

export type SetupBlock =
  | { type: "paragraph"; text: string }
  | CodeBlockData
  | { type: "list"; items: string[]; ordered?: boolean }
  | TableData
  | { type: "subheading"; text: string }
  | { type: "callout"; tone: CalloutTone; title: string; text?: string; items?: string[] }
  | { type: "tabs"; tabs: Array<{ label: string; blocks: SetupBlock[] }> }
  | { type: "accordion"; items: Array<{ question: string; answer: string }>; filterable?: boolean }
  | { type: "checklist"; items: string[] };

export interface SetupSubsection {
  id: string;
  number: string;
  title: string;
  blocks: SetupBlock[];
}

export const SETUP_INTRO =
  "Repository layout: the Git repository root contains `scrapeflow/`, `docs/`, `SETUP.md`, and `.github/`. Run application commands from `scrapeflow/` unless a step says otherwise.";
