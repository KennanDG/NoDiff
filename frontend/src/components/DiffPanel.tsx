import { DiffEditor } from "@monaco-editor/react";
import { FileCode2 } from "lucide-react";
import { useMemo } from "react";
import type { FileChange, RepositoryFile } from "../types";


type DiffPanelProps = {
  file: RepositoryFile | null;
  change: FileChange | null;
  isLoading?: boolean;
  error?: string | null;
};


const languageFromPath = (path: string) => {
  const extension = path.split(".").at(-1)?.toLowerCase();

  switch (extension) {
    case "c":
    case "cc":
    case "cpp":
    case "cxx":
    case "c++":
    case "h":
    case "hh":
    case "hpp":
    case "hxx":
      return "cpp";
    case "css":
      return "css";
    case "html":
      return "html";
    case "java":
      return "java";
    case "js":
    case "jsx":
      return "javascript";
    case "json":
      return "json";
    case "md":
      return "markdown";
    case "py":
      return "python";
    case "rs":
      return "rust";
    case "ts":
    case "tsx":
      return "typescript";
    case "yml":
    case "yaml":
      return "yaml";
    default:
      return "plaintext";
  }
};


const normalizeModelPath = (path: string, suffix: string) => {
  const normalized = path.replace(/\\/g, "/").replace(/^\/+/, "");
  return `file:///nodiff/${suffix}/${encodeURI(normalized)}`;
};


const truncate = (value: string, maxLength: number) => {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1)}…`;
};


const emptyFile = {
  path: "",
  content: "",
  language: "plaintext",
};


export const DiffPanel = ({
  file,
  change,
  isLoading = false,
  error = null,
}: DiffPanelProps) => {
  const effectiveFile = file ?? emptyFile;
  const path = change?.path ?? effectiveFile.path;
  const language = change?.language || effectiveFile.language || languageFromPath(path);
  const hasChange = Boolean(change);
  const original = change?.original ?? effectiveFile.content;
  const modified = change?.modified ?? effectiveFile.content;

  const originalModelPath = useMemo(
    () => normalizeModelPath(path || "untitled", "original"),
    [path],
  );
  const modifiedModelPath = useMemo(
    () => normalizeModelPath(path || "untitled", "modified"),
    [path],
  );

  return (
    <section className="flex min-h-0 flex-1 flex-col bg-panel">
      <header className="flex h-10 shrink-0 items-center gap-3 border-b border-line px-3">
        <div className="flex min-w-0 items-center gap-2 text-xs text-ink-soft">
          <FileCode2 size={14} className="shrink-0 text-accent" />
          <span className="truncate font-medium text-ink" title={path || "No file selected"}>
            {path ? truncate(path, 90) : "No file selected"}
          </span>
        </div>
        {hasChange && (
          <span className="ml-auto rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.16em] text-accent">
            {change?.status ?? "modified"}
          </span>
        )}
      </header>

      <div className="min-h-0 flex-1">
        {(() => {
          if (isLoading) {
            return <div className="grid h-full place-items-center text-xs text-muted">Loading file…</div>;
          }
          if (error) {
            return <div className="grid h-full place-items-center px-8 text-center text-xs leading-6 text-rose-300">{error}</div>;
          }
          if (file || change) {
            return (
              <DiffEditor
                key={`${path}:${hasChange ? "change" : "file"}`}
                original={original}
                modified={modified}
                language={language}
                originalLanguage={language}
                modifiedLanguage={language}
                originalModelPath={originalModelPath}
                modifiedModelPath={modifiedModelPath}
                theme="vs-dark"
                beforeMount={(monaco) => {
                  const typescript = monaco.languages.typescript;
                  const compilerOptions = {
                    allowJs: true,
                    allowNonTsExtensions: true,
                    esModuleInterop: true,
                    jsx: typescript.JsxEmit.ReactJSX,
                    module: typescript.ModuleKind.ESNext,
                    moduleResolution: typescript.ModuleResolutionKind.NodeJs,
                    noEmit: true,
                    skipLibCheck: true,
                    // Monaco's bundled TypeScript enum currently exposes targets
                    // through ES2020. Using that supported enum keeps the editor
                    // type-safe while still parsing modern JS/TS syntax.
                    target: typescript.ScriptTarget.ES2020,
                  };
                  const diagnosticsOptions = {
                    noSemanticValidation: true,
                    noSyntaxValidation: false,
                    noSuggestionDiagnostics: true,
                  };

                  typescript.typescriptDefaults.setCompilerOptions(compilerOptions);
                  typescript.javascriptDefaults.setCompilerOptions(compilerOptions);
                  typescript.typescriptDefaults.setDiagnosticsOptions(diagnosticsOptions);
                  typescript.javascriptDefaults.setDiagnosticsOptions(diagnosticsOptions);
                  typescript.typescriptDefaults.setEagerModelSync(true);
                  typescript.javascriptDefaults.setEagerModelSync(true);
                }}
                options={{
                  automaticLayout: true,
                  enableSplitViewResizing: true,
                  fontFamily: "JetBrains Mono, ui-monospace, SFMono-Regular, monospace",
                  fontSize: 12,
                  glyphMargin: false,
                  ignoreTrimWhitespace: false,
                  lineNumbers: "on",
                  minimap: { enabled: false },
                  originalEditable: false,
                  readOnly: true,
                  renderOverviewRuler: false,
                  scrollBeyondLastLine: false,
                  wordWrap: "off",
                }}
              />
            );
          }

          return (
            <div className="grid h-full place-items-center px-8 text-center text-sm leading-6 text-muted">
              Select a repository file or run the agent to review a diff.
            </div>
          );
        })()}
      </div>
    </section>
  );
};
