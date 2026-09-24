import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  CheckCircle2,
  CircleAlert,
  GitBranch,
  GitCommitHorizontal,
  GitPullRequest,
  FolderOpen,
  LoaderCircle,
  Plus,
  RefreshCcw,
  ShieldCheck,
} from "lucide-react";
import type {
  GitHubBranchSummary,
  GitHubRepositoryStatus,
  GitHubRepositorySummary,
} from "../lib/repositoryApi";

type SourceControlPageProps = {
  repoRoot: string;
  localRepoRoot: string;
  localDirectoryPickerAvailable: boolean;
  githubRepositories: GitHubRepositorySummary[];
  selectedGitHubRepository: string | null;
  githubLoading: boolean;
  githubError: string | null;
  onSelectGitHubRepository: (fullName: string) => Promise<boolean>;
  onUseLocalRepository: () => Promise<boolean>;
  onSelectLocalRepository: (repoRoot: string) => Promise<boolean>;
  onBrowseLocalRepository: () => Promise<string | null>;
  onRefreshGitHubRepositories: () => void;
  branches: GitHubBranchSummary[];
  currentBranch: string | null;
  branchesLoading: boolean;
  branchesError: string | null;
  onSwitchBranch: (branchName: string) => void;
  defaultBranch: string | null;
  repositoryPermissions: GitHubRepositorySummary["permissions"] | null;
  githubRepositoryStatus: GitHubRepositoryStatus | null;
  githubActionLoading: string | null;
  githubActionMessage: string | null;
  githubActionError: string | null;
  githubPullRequestUrl: string | null;
  committablePaths: string[];
  lastCommit: {
    branch: string;
    commitSha: string;
    committedFiles: string[];
  } | null;
  onTestGitHubConnection: () => void;
  onCreateGitHubBranch: (branch: string) => void;
  onPullGitHubBranch: () => void;
  onCommitGitHubChanges: (message: string, paths: string[]) => Promise<boolean>;
  onPushGitHubBranch: () => void;
  onCreateGitHubPullRequest: (request: {
    title: string;
    body: string;
    base: string;
    draft: boolean;
  }) => Promise<boolean>;
};

const FieldLabel = ({ children }: { children: ReactNode }) => (
  <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-muted">
    {children}
  </label>
);

const StatusList = ({
  title,
  paths,
  selectedPaths,
  approvedPaths,
  onToggle,
}: {
  title: string;
  paths: string[];
  selectedPaths: Set<string>;
  approvedPaths: Set<string>;
  onToggle: (path: string) => void;
}) => (
  <div className="rounded-lg border border-line bg-panel p-3">
    <div className="mb-2 flex items-center justify-between">
      <span className="text-xs font-semibold text-ink-soft">{title}</span>
      <span className="rounded bg-surface px-1.5 py-0.5 font-mono text-[9px] text-muted">
        {paths.length}
      </span>
    </div>
    {paths.length > 0 ? (
      <div className="max-h-40 space-y-1 overflow-auto">
        {paths.map((path) => (
          <label key={path} className="flex items-center gap-2 font-mono text-[10px] text-muted" title={path}>
            <input type="checkbox" checked={selectedPaths.has(path)}
              onChange={() => onToggle(path)} aria-label={`Include ${path} in commit`} />
            <span className="truncate">{path}{approvedPaths.has(path) ? " (agent applied)" : ""}</span>
          </label>
        ))}
      </div>
    ) : (
      <p className="text-[10px] text-faint">None</p>
    )}
  </div>
);

export const SourceControlPage = ({
  repoRoot,
  localRepoRoot,
  localDirectoryPickerAvailable,
  githubRepositories,
  selectedGitHubRepository,
  githubLoading,
  githubError,
  onSelectGitHubRepository,
  onUseLocalRepository,
  onSelectLocalRepository,
  onBrowseLocalRepository,
  onRefreshGitHubRepositories,
  branches,
  currentBranch,
  branchesLoading,
  branchesError,
  onSwitchBranch,
  defaultBranch,
  repositoryPermissions,
  githubRepositoryStatus,
  githubActionLoading,
  githubActionMessage,
  githubActionError,
  githubPullRequestUrl,
  committablePaths,
  lastCommit,
  onTestGitHubConnection,
  onCreateGitHubBranch,
  onPullGitHubBranch,
  onCommitGitHubChanges,
  onPushGitHubBranch,
  onCreateGitHubPullRequest,
}: SourceControlPageProps) => {
  const [localPath, setLocalPath] = useState(localRepoRoot);
  const committedRepositorySource = selectedGitHubRepository
    ? `github:${selectedGitHubRepository}`
    : "local";
  const [repositorySource, setRepositorySource] = useState(committedRepositorySource);
  const sourceChangeGenerationRef = useRef(0);
  const [newBranch, setNewBranch] = useState("agent/");
  const [commitMessage, setCommitMessage] = useState("");
  const [manualSelections, setManualSelections] = useState<string[]>([]);
  const [excludedApprovals, setExcludedApprovals] = useState<string[]>([]);
  const [prTitle, setPrTitle] = useState("");
  const [prBody, setPrBody] = useState("");
  const [prBase, setPrBase] = useState(defaultBranch ?? "main");
  const [draft, setDraft] = useState(true);
  const [lastCommitVisible, setLastCommitVisible] = useState(true);

  useEffect(() => {
    if (defaultBranch) setPrBase(defaultBranch);
  }, [defaultBranch]);

  useEffect(() => {
    setLastCommitVisible(true);
  }, [lastCommit?.commitSha]);


  useEffect(() => {
    setLocalPath(localRepoRoot);
  }, [localRepoRoot]);

  // Keep the selector responsive during a slow clone/import. The parent commits
  // selectedGitHubRepository only after the backend import succeeds; until then
  // this local value reflects the user's pending choice instead of snapping back
  // to "Local".
  useEffect(() => {
    setRepositorySource(committedRepositorySource);
  }, [committedRepositorySource]);

  useEffect(() => {
    setManualSelections([]);
    setExcludedApprovals([]);
  }, [selectedGitHubRepository, currentBranch]);

  const changedPaths = new Set([
    ...(githubRepositoryStatus?.staged_files ?? []),
    ...(githubRepositoryStatus?.unstaged_files ?? []),
    ...(githubRepositoryStatus?.untracked_files ?? []),
  ]);
  const approvedPaths = new Set(committablePaths);
  const selectedPaths = new Set([
    ...committablePaths.filter((path) => !excludedApprovals.includes(path)),
    ...manualSelections.filter((path) => changedPaths.has(path)),
  ]);
  const toggleCommitPath = (path: string) => {
    if (approvedPaths.has(path)) {
      setExcludedApprovals((current) => current.includes(path) ? current.filter((item) => item !== path) : [...current, path]);
    } else {
      setManualSelections((current) => current.includes(path) ? current.filter((item) => item !== path) : [...current, path]);
    }
  };

  const localRepoName = useMemo(
    () => localRepoRoot.split(/[\\/]/).filter(Boolean).at(-1) ?? "Select folder",
    [localRepoRoot],
  );
  const selectedSummary = useMemo(
    () => githubRepositories.find((item) => item.full_name === selectedGitHubRepository) ?? null,
    [githubRepositories, selectedGitHubRepository],
  );

  const busy = githubActionLoading !== null;
  const repositoryImporting = githubActionLoading === "repository";
  const localRepositorySaving = githubActionLoading === "local-repository";
  // A GitHub import is intentionally recoverable: while it is running the user
  // can still choose Local/Browse. Other Git mutations keep repository controls
  // locked to avoid racing a branch/commit/push operation.
  const repositoryControlsLocked = busy && !repositoryImporting;
  const canPush = Boolean(repositoryPermissions?.push && selectedGitHubRepository);
  const canCommit = canPush && selectedPaths.size > 0 && commitMessage.trim().length > 0;
  const canOpenPr = Boolean(
    canPush &&
      currentBranch &&
      prBase &&
      currentBranch !== prBase &&
      prTitle.trim() &&
      githubRepositoryStatus &&
      !githubRepositoryStatus.dirty,
  );

  const handleRepositorySourceChange = async (value: string) => {
    const sourceChangeGeneration = ++sourceChangeGenerationRef.current;
    setRepositorySource(value);

    const selected = value === "local"
      ? await onUseLocalRepository()
      : value.startsWith("github:")
        ? await onSelectGitHubRepository(value.slice("github:".length))
        : false;

    // Ignore the completion of an older selection after the user has already
    // picked another source. This prevents a slow import from snapping the
    // selector back over a newer Local/GitHub choice.
    if (sourceChangeGeneration !== sourceChangeGenerationRef.current) return;

    if (!selected) {
      setRepositorySource(committedRepositorySource);
    }
  };

  const handleSelectLocalRepository = async () => {
    const sourceChangeGeneration = ++sourceChangeGenerationRef.current;
    const selected = await onSelectLocalRepository(localPath);
    if (sourceChangeGeneration !== sourceChangeGenerationRef.current) return;
    if (selected) setRepositorySource("local");
  };

  const handleBrowseLocalRepository = async () => {
    const sourceChangeGeneration = ++sourceChangeGenerationRef.current;
    const selectedPath = await onBrowseLocalRepository();
    if (sourceChangeGeneration !== sourceChangeGenerationRef.current) return;
    if (selectedPath) {
      setLocalPath(selectedPath);
      setRepositorySource("local");
    }
  };

  const handleCommit = async () => {
    const committed = await onCommitGitHubChanges(commitMessage.trim(), [...selectedPaths]);
    if (committed) {
      setCommitMessage("");
      setManualSelections([]);
      setExcludedApprovals([]);
    }
  };

  const handleCreatePullRequest = async () => {
    const created = await onCreateGitHubPullRequest({
      title: prTitle.trim(),
      body: prBody,
      base: prBase,
      draft,
    });

    if (created) {
      setPrTitle("");
      setPrBody("");
      setPrBase(defaultBranch ?? "main");
      setDraft(true);
    }
  };

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col bg-canvas">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-line px-5">
        <div className="flex items-center gap-2">
          <GitBranch size={16} className="text-accent-light" />
          <h1 className="text-sm font-semibold text-ink">Source control</h1>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={onRefreshGitHubRepositories}
          disabled={githubLoading}
        >
          {githubLoading ? <LoaderCircle size={12} className="animate-spin" /> : <RefreshCcw size={12} />}
          Refresh repositories
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-auto p-5">
        <div className="mx-auto grid max-w-6xl gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
          <div className="space-y-4">
            <div className="rounded-xl border border-line bg-panel-soft p-4">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-ink">Repository</h2>
                  <p className="mt-1 text-[11px] text-muted">
                    Choose the managed checkout used by the coding agent and Git operations.
                  </p>
                </div>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={onTestGitHubConnection}
                  disabled={busy}
                >
                  {githubActionLoading === "test" ? (
                    <LoaderCircle size={12} className="animate-spin" />
                  ) : (
                    <ShieldCheck size={12} />
                  )}
                  Test connection
                </button>
              </div>

              <FieldLabel>Repository source</FieldLabel>
              <div className="flex items-center gap-2">
                <select
                  value={repositorySource}
                  disabled={githubLoading || repositoryControlsLocked}
                  onChange={(event) => void handleRepositorySourceChange(event.target.value)}
                  className="min-w-0 flex-1 rounded-md border border-line bg-surface px-3 py-2 text-xs text-ink outline-none hover:border-line-strong focus:border-accent/70"
                >
                <option value="local">Local · {localRepoName}</option>
                  {githubRepositories.map((repository) => (
                    <option key={repository.id} value={`github:${repository.full_name}`}>
                      GitHub · {repository.full_name}{repository.private ? " (private)" : ""}
                    </option>
                  ))}
                </select>
                {repositoryImporting ? (
                  <LoaderCircle
                    size={14}
                    className="shrink-0 animate-spin text-accent-light"
                    aria-label="Importing GitHub repository"
                  />
                ) : null}
              </div>

              <p className="mt-2 truncate font-mono text-[10px] text-faint" title={repoRoot}>
                {repoRoot}
              </p>

              <div className="mt-4 rounded-lg border border-line bg-surface p-3">
                <FieldLabel>Local repository root</FieldLabel>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <input
                    value={localPath}
                    onChange={(event) => setLocalPath(event.target.value)}
                    className="min-w-0 flex-1 rounded-md border border-line bg-panel px-3 py-2 font-mono text-[11px] text-ink outline-none focus:border-accent/70"
                    placeholder="C:\\Users\\you\\source\\repository"
                  />
                  <button
                    type="button"
                    className="secondary-button h-8"
                    disabled={repositoryControlsLocked || !localDirectoryPickerAvailable}
                    onClick={() => void handleBrowseLocalRepository()}
                    title={
                      localDirectoryPickerAvailable
                        ? "Open the desktop directory picker"
                        : "Directory browsing requires the desktop bridge"
                    }
                  >
                    <FolderOpen size={12} />
                    Browse
                  </button>
                  <button
                    type="button"
                    className="primary-button h-8"
                    disabled={repositoryControlsLocked || !localPath.trim()}
                    onClick={() => void handleSelectLocalRepository()}
                  >
                    {localRepositorySaving ? (
                      <LoaderCircle size={12} className="animate-spin" />
                    ) : (
                      <FolderOpen size={12} />
                    )}
                    Use folder
                  </button>
                </div>
                <p className="mt-2 text-[10px] leading-4 text-faint">
                  The path must be visible to the backend process. Browser-only builds can
                  enter a backend-local path; desktop builds can expose a native picker through
                  window.desktop.selectDirectory.
                </p>
              </div>

              {githubError ? (
                <div className="mt-3 flex items-start gap-2 rounded-md border border-rose-500/20 bg-rose-500/8 p-2.5 text-[10px] leading-4 text-rose-300">
                  <CircleAlert size={13} className="mt-0.5 shrink-0" />
                  {githubError}
                </div>
              ) : null}

              {selectedGitHubRepository ? (
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div>
                    <div className="flex items-center justify-between">
                      <FieldLabel>Current branch</FieldLabel>
                      {githubActionLoading === "switch" ? (
                        <LoaderCircle size={11} className="mb-1 animate-spin text-accent-light" />
                      ) : null}
                    </div>
                    <select
                      value={currentBranch ?? ""}
                      disabled={branchesLoading || busy}
                      onChange={(event) => event.target.value && onSwitchBranch(event.target.value)}
                      className="w-full rounded-md border border-line bg-surface px-3 py-2 text-xs text-ink outline-none hover:border-line-strong focus:border-accent/70"
                    >
                      {branches.map((branch) => (
                        <option key={branch.name} value={branch.name}>
                          {branch.name}
                        </option>
                      ))}
                    </select>
                    {branchesError ? <p className="mt-1 text-[10px] text-rose-300">{branchesError}</p> : null}
                    <p className="mt-1 text-[10px] leading-4 text-faint">
                      Local staged, unstaged, and untracked files are saved per branch and restored when you return.
                    </p>
                  </div>

                  <div>
                    <FieldLabel>Create agent branch</FieldLabel>
                    <div className="flex gap-2">
                      <input
                        value={newBranch}
                        onChange={(event) => setNewBranch(event.target.value)}
                        className="min-w-0 flex-1 rounded-md border border-line bg-surface px-3 py-2 text-xs text-ink outline-none focus:border-accent/70"
                        placeholder="agent/feature-name"
                      />
                      <button
                        type="button"
                        className="secondary-button h-8"
                        disabled={!newBranch.trim() || busy || !repositoryPermissions?.push}
                        onClick={() => onCreateGitHubBranch(newBranch.trim())}
                      >
                        {githubActionLoading === "branch" ? (
                          <LoaderCircle size={12} className="animate-spin" />
                        ) : (
                          <Plus size={12} />
                        )}
                        Create
                      </button>
                    </div>
                  </div>
                </div>
              ) : null}

              {githubActionError ? (
                <div className="mt-3 flex items-start gap-2 rounded-md border border-rose-500/20 bg-rose-500/8 p-2.5 text-[10px] leading-4 text-rose-300">
                  <CircleAlert size={13} className="mt-0.5 shrink-0" />
                  {githubActionError}
                </div>
              ) : null}

              {selectedSummary ? (
                <div className="mt-4 grid grid-cols-2 gap-2 text-[10px] text-muted sm:grid-cols-4">
                  <div className="rounded-md border border-line bg-surface p-2">
                    <span className="block text-faint">Default</span>
                    <span className="font-mono text-ink-soft">{selectedSummary.default_branch}</span>
                  </div>
                  <div className="rounded-md border border-line bg-surface p-2">
                    <span className="block text-faint">Push</span>
                    <span className="text-ink-soft">{selectedSummary.permissions.push ? "Allowed" : "Denied"}</span>
                  </div>
                  <div className="rounded-md border border-line bg-surface p-2">
                    <span className="block text-faint">Visibility</span>
                    <span className="text-ink-soft">{selectedSummary.private ? "Private" : "Public"}</span>
                  </div>
                  <div className="rounded-md border border-line bg-surface p-2">
                    <span className="block text-faint">Policy</span>
                    <span className="text-ink-soft">PR-first</span>
                  </div>
                </div>
              ) : null}
            </div>

            {selectedGitHubRepository ? (
              <div className="rounded-xl border border-line bg-panel-soft p-4">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-semibold text-ink">Working tree</h2>
                    <p className="mt-1 text-[11px] text-muted">
                      Agent applied files are selected by default. Select any other files you reviewed before committing.
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={onPullGitHubBranch}
                      disabled={busy}
                    >
                      {githubActionLoading === "pull" ? (
                        <LoaderCircle size={12} className="animate-spin" />
                      ) : (
                        <ArrowDownToLine size={12} />
                      )}
                      Pull
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => {
                        setLastCommitVisible(false);
                        onPushGitHubBranch();
                      }}
                      disabled={busy || !canPush}
                    >
                      {githubActionLoading === "push" ? (
                        <LoaderCircle size={12} className="animate-spin" />
                      ) : (
                        <ArrowUpFromLine size={12} />
                      )}
                      Push
                    </button>
                  </div>
                </div>

                <div className="grid gap-3 md:grid-cols-3">
                  <StatusList title="Staged" paths={githubRepositoryStatus?.staged_files ?? []} selectedPaths={selectedPaths} approvedPaths={approvedPaths} onToggle={toggleCommitPath} />
                  <StatusList title="Unstaged" paths={githubRepositoryStatus?.unstaged_files ?? []} selectedPaths={selectedPaths} approvedPaths={approvedPaths} onToggle={toggleCommitPath} />
                  <StatusList title="Untracked" paths={githubRepositoryStatus?.untracked_files ?? []} selectedPaths={selectedPaths} approvedPaths={approvedPaths} onToggle={toggleCommitPath} />
                </div>

                {lastCommit && lastCommitVisible ? (
                  <div className="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/6 p-3">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 size={13} className="text-emerald-300" />
                        <span className="text-xs font-semibold text-emerald-200">Last committed files</span>
                      </div>
                      <span className="font-mono text-[9px] text-emerald-300/80">
                        {lastCommit.branch} · {lastCommit.commitSha.slice(0, 7)}
                      </span>
                    </div>
                    <div className="max-h-40 space-y-1 overflow-auto">
                      {lastCommit.committedFiles.map((path) => (
                        <div key={path} className="truncate font-mono text-[10px] text-emerald-200/80" title={path}>
                          {path}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto]">
                  <div>
                    <FieldLabel>Commit message</FieldLabel>
                    <input
                      value={commitMessage}
                      onChange={(event) => setCommitMessage(event.target.value)}
                      className="w-full rounded-md border border-line bg-surface px-3 py-2 text-xs text-ink outline-none focus:border-accent/70"
                      placeholder="Describe the approved agent change"
                    />
                  </div>
                  <button
                    type="button"
                    className="primary-button mt-auto h-8"
                    disabled={!canCommit || busy}
                    onClick={() => void handleCommit()}
                  >
                    {githubActionLoading === "commit" ? (
                      <LoaderCircle size={12} className="animate-spin" />
                    ) : (
                      <GitCommitHorizontal size={12} />
                    )}
                    Commit {selectedPaths.size} file{selectedPaths.size === 1 ? "" : "s"}
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-line bg-panel-soft p-4">
              <div className="mb-4 flex items-center gap-2">
                <GitPullRequest size={15} className="text-accent-light" />
                <div>
                  <h2 className="text-sm font-semibold text-ink">Pull request</h2>
                  <p className="mt-1 text-[11px] text-muted">Push the agent branch before opening the PR.</p>
                </div>
              </div>

              <div className="space-y-3">
                <div>
                  <FieldLabel>Title</FieldLabel>
                  <input
                    value={prTitle}
                    onChange={(event) => setPrTitle(event.target.value)}
                    className="w-full rounded-md border border-line bg-surface px-3 py-2 text-xs text-ink outline-none focus:border-accent/70"
                    placeholder="Agent change summary"
                  />
                </div>
                <div>
                  <FieldLabel>Base branch</FieldLabel>
                  <select
                    value={prBase}
                    onChange={(event) => setPrBase(event.target.value)}
                    className="w-full rounded-md border border-line bg-surface px-3 py-2 text-xs text-ink outline-none focus:border-accent/70"
                  >
                    {branches.map((branch) => (
                      <option key={branch.name} value={branch.name}>
                        {branch.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <FieldLabel>Description</FieldLabel>
                  <textarea
                    value={prBody}
                    onChange={(event) => setPrBody(event.target.value)}
                    rows={7}
                    className="w-full resize-y rounded-md border border-line bg-surface px-3 py-2 text-xs leading-5 text-ink outline-none focus:border-accent/70"
                    placeholder="What changed, why, and how it was validated"
                  />
                </div>
                <label className="flex cursor-pointer items-center gap-2 text-[11px] text-muted">
                  <input
                    type="checkbox"
                    checked={draft}
                    onChange={(event) => setDraft(event.target.checked)}
                    className="accent-accent"
                  />
                  Open as draft
                </label>
                <button
                  type="button"
                  className="primary-button h-8 w-full justify-center"
                  disabled={!canOpenPr || busy}
                  onClick={() => void handleCreatePullRequest()}
                >
                  {githubActionLoading === "pr" ? (
                    <LoaderCircle size={12} className="animate-spin" />
                  ) : (
                    <GitPullRequest size={12} />
                  )}
                  Create {draft ? "draft " : ""}pull request
                </button>
              </div>
            </div>

            <div className="rounded-xl border border-line bg-panel-soft p-4">
              <h2 className="text-sm font-semibold text-ink">Repository status</h2>
              <div className="mt-3 space-y-2 text-[11px]">
                <div className="flex justify-between gap-3">
                  <span className="text-muted">Branch</span>
                  <span className="font-mono text-ink-soft">{currentBranch ?? "Local only"}</span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-muted">Ahead / behind</span>
                  <span className="font-mono text-ink-soft">
                    {githubRepositoryStatus
                      ? `${githubRepositoryStatus.ahead} / ${githubRepositoryStatus.behind}`
                      : "—"}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-muted">Working tree</span>
                  <span className="text-ink-soft">
                    {githubRepositoryStatus?.dirty ? "Dirty" : "Clean"}
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-muted">Default branch</span>
                  <span className="font-mono text-ink-soft">{defaultBranch ?? "—"}</span>
                </div>
              </div>
            </div>

            {githubActionMessage ? (
              <div className="flex items-start gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/8 p-3 text-[11px] leading-5 text-emerald-300">
                <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
                <div>
                  <p>{githubActionMessage}</p>
                  {githubPullRequestUrl ? (
                    <a
                      href={githubPullRequestUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 inline-block underline underline-offset-2"
                    >
                      Open pull request
                    </a>
                  ) : null}
                </div>
              </div>
            ) : null}

          </div>
        </div>
      </div>
    </section>
  );
}
