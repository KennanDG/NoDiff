import type { RepositoryFile, RepositoryTreeResponse } from "../types";

type ApiClientConfig = {
  apiBaseUrl: string;
  apiKey?: string;
};

type RepositoryRequest = ApiClientConfig & {
  repoRoot: string;
};

export type GitHubStatus = {
  connected: boolean;
  token_kind: "user" | "installation";
  account?: string | null;
};

export type GitHubRepositorySummary = {
  id: number;
  full_name: string;
  name: string;
  owner: string;
  private: boolean;
  default_branch: string;
  clone_url: string;
  html_url: string;
  updated_at?: string | null;
  permissions: {
    admin: boolean;
    maintain: boolean;
    push: boolean;
    triage: boolean;
    pull: boolean;
  };
};

export type GitHubRepositoryImportResponse = {
  full_name: string;
  ref: string;
  repo_root: string;
  reused_existing_checkout: boolean;
  previous_ref?: string | null;
  saved_previous_changes: boolean;
  restored_target_changes: boolean;
};

export type SavedLocalRepositoryRoot = {
  repo_root: string | null;
  available: boolean;
};

// TODO: Replace renderer API-key access with a short-lived backend session token.
const apiUrl = (
  path: string,
  config: ApiClientConfig,
  params: Record<string, string | number | undefined>,
) => {
  const url = new URL(path, config.apiBaseUrl);

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }

  return url;
};

const authHeaders = (apiKey?: string): HeadersInit => {
  return apiKey ? { "x-api-key": apiKey } : {};
};

const headersToRecord = (headers?: HeadersInit): Record<string, string> => {
  if (!headers) return {};

  const normalized = new Headers(headers);
  const result: Record<string, string> = {};
  normalized.forEach((value, key) => {
    result[key] = value;
  });
  return result;
};

const apiFetch = async (
  url: URL,
  init: RequestInit = {},
  timeoutMs?: number,
): Promise<Response> => {
  const desktopRequest = window.desktop?.apiRequest;

  if (desktopRequest) {
    const headers = headersToRecord(init.headers);
    // Electron main injects the current sidecar key. Do not shuttle it back over
    // IPC when the desktop bridge is available.
    delete headers["x-api-key"];

    const result = await desktopRequest({
      url: url.toString(),
      method: init.method ?? "GET",
      headers,
      body: typeof init.body === "string" ? init.body : null,
      timeoutMs,
    });

    return new Response(result.body, {
      status: result.status,
      statusText: result.statusText,
      headers: result.headers,
    });
  }

  return fetch(url, init);
};

const GITHUB_IMPORT_TIMEOUT_MS = 420_000;

const fetchWithTimeout = async (
  url: URL,
  init: RequestInit,
  {
    operation,
    timeoutMs,
  }: {
    operation: string;
    timeoutMs: number;
  },
): Promise<Response> => {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    if (window.desktop?.apiRequest) {
      return await apiFetch(
        url,
        {
          ...init,
          credentials: "omit",
          cache: "no-store",
        },
        timeoutMs,
      );
    }

    return await apiFetch(url, {
      ...init,
      signal: controller.signal,
      credentials: "omit",
      cache: "no-store",
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    const timedOut =
      (error instanceof DOMException && error.name === "AbortError") ||
      (error instanceof Error && error.name === "TimeoutError") ||
      /timeout|timed out|aborted due to timeout/i.test(detail);

    if (timedOut) {
      if (window.desktop?.apiRequest) {
        throw new Error(
          `${operation} timed out after ${Math.round(timeoutMs / 1000)} seconds while Electron main was waiting for FastAPI. ` +
            "Desktop API requests bypass browser CORS, so no OPTIONS preflight is expected. Check the Electron terminal for [desktop-api] and [github-import] timing logs.",
        );
      }

      throw new Error(
        `${operation} timed out after ${Math.round(timeoutMs / 1000)} seconds.`,
      );
    }

    if (window.desktop?.apiRequest) {
      throw new Error(`${operation} failed through the Electron desktop API bridge. ${detail}`);
    }

    throw new Error(`${operation} could not be completed by the renderer. ${detail}`);
  } finally {
    clearTimeout(timeout);
  }
};

async function readJson<T>(response: Response): Promise<T> {
  if (response.ok) return (await response.json()) as T;

  let message = `${response.status} ${response.statusText}`;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (body.detail) {
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }
  } catch {
    // Keep the HTTP status message.
  }

  throw new Error(message);
}

export const fetchRepositoryTree = async ({
  apiBaseUrl,
  apiKey,
  repoRoot,
  maxDepth = 8,
  maxEntries = 1500,
}: RepositoryRequest & {
  maxDepth?: number;
  maxEntries?: number;
}): Promise<RepositoryTreeResponse> => {
  const url = apiUrl("/coding-agent/repository/tree", { apiBaseUrl, apiKey }, {
    repo_root: repoRoot,
    max_depth: maxDepth,
    max_entries: maxEntries,
  });

  const response = await apiFetch(url, { headers: authHeaders(apiKey) });
  return readJson<RepositoryTreeResponse>(response);
};

export const fetchRepositoryFile = async ({
  apiBaseUrl,
  apiKey,
  repoRoot,
  path,
}: RepositoryRequest & { path: string }): Promise<RepositoryFile> => {
  const url = apiUrl("/coding-agent/repository/file", { apiBaseUrl, apiKey }, {
    repo_root: repoRoot,
    path,
  });

  const response = await apiFetch(url, { headers: authHeaders(apiKey) });
  return readJson<RepositoryFile>(response);
};


export const fetchSavedLocalRepositoryRoot = async ({
  apiBaseUrl,
  apiKey,
}: ApiClientConfig): Promise<SavedLocalRepositoryRoot> => {
  const response = await apiFetch(apiUrl("/admin/local-repository", { apiBaseUrl, apiKey }, {}), {
    headers: authHeaders(apiKey),
  });
  return readJson<SavedLocalRepositoryRoot>(response);
};

export const saveLocalRepositoryRoot = async ({
  apiBaseUrl,
  apiKey,
  repoRoot,
}: RepositoryRequest): Promise<SavedLocalRepositoryRoot> => {
  const response = await apiFetch(apiUrl("/admin/local-repository", { apiBaseUrl, apiKey }, {}), {
    method: "PUT",
    headers: {
      "content-type": "application/json",
      ...authHeaders(apiKey),
    },
    body: JSON.stringify({ repo_root: repoRoot }),
  });
  return readJson<SavedLocalRepositoryRoot>(response);
};

export const fetchGitHubStatus = async ({
  apiBaseUrl,
  apiKey,
}: ApiClientConfig): Promise<GitHubStatus> => {
  const response = await apiFetch(apiUrl("/github/status", { apiBaseUrl, apiKey }, {}), {
    headers: authHeaders(apiKey),
  });
  return readJson<GitHubStatus>(response);
};

export const fetchGitHubRepositories = async ({
  apiBaseUrl,
  apiKey,
}: ApiClientConfig): Promise<GitHubRepositorySummary[]> => {
  const response = await apiFetch(
    apiUrl("/github/repositories", { apiBaseUrl, apiKey }, { per_page: 100 }),
    { headers: authHeaders(apiKey) },
  );
  return readJson<GitHubRepositorySummary[]>(response);
};

export const importGitHubRepository = async ({
  apiBaseUrl,
  apiKey,
  fullName,
  ref,
  refresh = false,
}: ApiClientConfig & {
  fullName: string;
  ref?: string | null;
  refresh?: boolean;
}): Promise<GitHubRepositoryImportResponse> => {
  const url = apiUrl("/github/repositories/import", { apiBaseUrl, apiKey }, {});

  if (import.meta.env.DEV) {
    console.debug("[repositoryApi] importing GitHub repository", {
      url: url.toString(),
      fullName,
      ref: ref ?? null,
      refresh,
    });
  }

  const response = await fetchWithTimeout(
    url,
    {
      method: "POST",
      headers: {
        "accept": "application/json",
        "content-type": "application/json",
        ...authHeaders(apiKey),
      },
      body: JSON.stringify({
        full_name: fullName,
        ref: ref ?? null,
        refresh,
      }),
    },
    {
      operation: `Importing ${fullName}`,
      timeoutMs: GITHUB_IMPORT_TIMEOUT_MS,
    },
  );

  if (import.meta.env.DEV) {
    console.debug("[repositoryApi] GitHub import response", {
      status: response.status,
      ok: response.ok,
      url: response.url,
      type: response.type,
    });
  }

  return readJson<GitHubRepositoryImportResponse>(response);
};

export type GitHubBranchSummary = {
  name: string;
  sha: string;
};

export const fetchGitHubBranches = async ({
  apiBaseUrl,
  apiKey,
  fullName,
  page = 1,
  perPage = 100,
}: ApiClientConfig & {
  fullName: string;
  page?: number;
  perPage?: number;
}): Promise<GitHubBranchSummary[]> => {
  const response = await apiFetch(
    apiUrl("/github/repositories/branches", { apiBaseUrl, apiKey }, { full_name: fullName, page, per_page: perPage }),
    { headers: authHeaders(apiKey) },
  );
  return readJson<GitHubBranchSummary[]>(response);
};


export type GitHubConnectionTestResponse = {
  connected: boolean;
  api_connected: boolean;
  git_available: boolean;
  git_transport_connected: boolean;
  workspace_writable: boolean;
  token_kind: "user" | "installation";
  account?: string | null;
  full_name?: string | null;
  default_branch?: string | null;
  permissions: GitHubRepositorySummary["permissions"];
  message: string;
};

export type GitHubRepositoryStatus = {
  full_name: string;
  repo_root: string;
  branch: string;
  default_branch: string;
  head_sha: string;
  upstream?: string | null;
  ahead: number;
  behind: number;
  dirty: boolean;
  staged_files: string[];
  unstaged_files: string[];
  untracked_files: string[];
};

export type GitHubCreateBranchResponse = {
  full_name: string;
  branch: string;
  sha: string;
};

export type GitHubPullResponse = {
  full_name: string;
  branch: string;
  head_sha: string;
  changed: boolean;
};

export type GitHubCommitResponse = {
  full_name: string;
  branch: string;
  commit_sha: string;
  committed_files: string[];
};

export type GitHubPushResponse = {
  full_name: string;
  branch: string;
  commit_sha: string;
  pushed: boolean;
};

export type GitHubPullRequestResponse = {
  full_name: string;
  number: number;
  title: string;
  html_url: string;
  base: string;
  head: string;
  draft: boolean;
  created: boolean;
};

const postJson = async <T>(
  path: string,
  config: ApiClientConfig,
  body: Record<string, unknown>,
): Promise<T> => {
  const response = await apiFetch(apiUrl(path, config, {}), {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...authHeaders(config.apiKey),
    },
    body: JSON.stringify(body),
  });
  return readJson<T>(response);
};

export const testGitHubConnection = async ({
  apiBaseUrl,
  apiKey,
  fullName,
}: ApiClientConfig & { fullName?: string | null }): Promise<GitHubConnectionTestResponse> => {
  const response = await apiFetch(
    apiUrl("/github/connection-test", { apiBaseUrl, apiKey }, { full_name: fullName ?? undefined }),
    { headers: authHeaders(apiKey) },
  );
  return readJson<GitHubConnectionTestResponse>(response);
};

export const fetchGitHubRepositoryStatus = async ({
  apiBaseUrl,
  apiKey,
  fullName,
}: ApiClientConfig & { fullName: string }): Promise<GitHubRepositoryStatus> => {
  const response = await apiFetch(
    apiUrl("/github/repositories/status", { apiBaseUrl, apiKey }, { full_name: fullName }),
    { headers: authHeaders(apiKey) },
  );
  return readJson<GitHubRepositoryStatus>(response);
};

export const createGitHubBranch = async ({
  apiBaseUrl,
  apiKey,
  fullName,
  branch,
  base,
}: ApiClientConfig & {
  fullName: string;
  branch: string;
  base?: string | null;
}): Promise<GitHubCreateBranchResponse> => {
  return postJson<GitHubCreateBranchResponse>(
    "/github/repositories/branches/create",
    { apiBaseUrl, apiKey },
    { full_name: fullName, branch, base: base ?? null },
  );
};

export const pullGitHubBranch = async ({
  apiBaseUrl,
  apiKey,
  fullName,
}: ApiClientConfig & { fullName: string }): Promise<GitHubPullResponse> => {
  return postJson<GitHubPullResponse>(
    "/github/repositories/pull",
    { apiBaseUrl, apiKey },
    { full_name: fullName },
  );
};

export const commitGitHubChanges = async ({
  apiBaseUrl,
  apiKey,
  fullName,
  message,
  paths,
}: ApiClientConfig & {
  fullName: string;
  message: string;
  paths: string[];
}): Promise<GitHubCommitResponse> => {
  return postJson<GitHubCommitResponse>(
    "/github/repositories/commit",
    { apiBaseUrl, apiKey },
    { full_name: fullName, message, paths },
  );
};

export const pushGitHubBranch = async ({
  apiBaseUrl,
  apiKey,
  fullName,
}: ApiClientConfig & { fullName: string }): Promise<GitHubPushResponse> => {
  return postJson<GitHubPushResponse>(
    "/github/repositories/push",
    { apiBaseUrl, apiKey },
    { full_name: fullName },
  );
};

export const createGitHubPullRequest = async ({
  apiBaseUrl,
  apiKey,
  fullName,
  title,
  body,
  base,
  head,
  draft = true,
}: ApiClientConfig & {
  fullName: string;
  title: string;
  body?: string;
  base?: string | null;
  head?: string | null;
  draft?: boolean;
}): Promise<GitHubPullRequestResponse> => {
  return postJson<GitHubPullRequestResponse>(
    "/github/repositories/pull-requests",
    { apiBaseUrl, apiKey },
    {
      full_name: fullName,
      title,
      body: body ?? "",
      base: base ?? null,
      head: head ?? null,
      draft,
      maintainer_can_modify: true,
    },
  );
};
