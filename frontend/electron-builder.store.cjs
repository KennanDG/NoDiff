const requiredEnvironmentValue = (name) => {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(
      `${name} is required for a Microsoft Store build. ` +
        "Reserve NoDiff in Partner Center, open Product identity, and copy the exact value.",
    );
  }
  return value;
};

const storeVersion = (process.env.MICROSOFT_STORE_VERSION || "1.0.0").trim();
const versionParts = storeVersion.split(".").map((part) => Number.parseInt(part, 10));

if (
  versionParts.length < 1 ||
  versionParts.length > 3 ||
  versionParts.some((part) => !Number.isInteger(part) || part < 0 || part > 65535) ||
  versionParts[0] === 0
) {
  throw new Error(
    "MICROSOFT_STORE_VERSION must be a 1-3 part numeric version with a non-zero major version, e.g. 1.0.0.",
  );
}

module.exports = {
  appId: "com.kennangauthier.nodiff",
  productName: "NoDiff",

  // package.json is currently 0.1.0, which cannot be used as a Microsoft Store
  // package version because Windows requires a non-zero first component. The
  // metadata merge occurs before electron-builder creates AppInfo/MSIX metadata.
  extraMetadata: {
    version: storeVersion,
  },

  files: ["dist/**", "dist-electron/**", "package.json"],
  extraResources: [
    {
      from: "../backend/dist/nodiff-agent-runtime",
      to: "backend/nodiff-agent-runtime",
      filter: ["**/*"],
    },
  ],
  directories: {
    output: "release-store",
    buildResources: "build",
  },
  win: {
    target: [
      {
        target: "msix",
        arch: ["x64"],
      },
    ],
    icon: "build/icon.ico",
    executableName: "NoDiff",
  },
  msix: {
    applicationId: "NoDiff",
    identityName: requiredEnvironmentValue("MICROSOFT_STORE_IDENTITY_NAME"),
    publisher: requiredEnvironmentValue("MICROSOFT_STORE_PUBLISHER"),
    publisherDisplayName: requiredEnvironmentValue(
      "MICROSOFT_STORE_PUBLISHER_DISPLAY_NAME",
    ),
    displayName: (process.env.MICROSOFT_STORE_DISPLAY_NAME || "NoDiff").trim(),
    languages: ["en-US"],
    backgroundColor: "#090B10",
    minVersion: "10.0.17763.0",
    artifactName: "NoDiff-${version}-${arch}.${ext}",
  },
};
