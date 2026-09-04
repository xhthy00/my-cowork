#!/usr/bin/env node
/**
 * Trigger GitHub Actions cloud packaging. Does not run local electron-builder
 * and does not change `npm run package:win`.
 *
 *   node scripts/release-ci.cjs --dispatch     # push branch, workflow_dispatch (artifacts)
 *   node scripts/release-ci.cjs --dispatch --watch
 *   node scripts/release-ci.cjs                # tag current version + push (GitHub Release)
 *   node scripts/release-ci.cjs --patch        # 0.0.4 -> 0.0.5, tag, push
 *   node scripts/release-ci.cjs --minor
 *   node scripts/release-ci.cjs --major
 *   node scripts/release-ci.cjs 0.0.5
 *   node scripts/release-ci.cjs --dry-run
 */
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const PKG_PATH = path.join(ROOT, "package.json");
const SEMVER = /^\d+\.\d+\.\d+$/;
const REPO = "xhthy00/my-cowork";
const WORKFLOW = "build.yml";
const WIN = process.platform === "win32";

function fail(message) {
  console.error(`error: ${message}`);
  process.exit(1);
}

function run(command, args, opts = {}) {
  const result = spawnSync(command, args, {
    cwd: ROOT,
    encoding: "utf8",
    stdio: opts.stdio || "pipe",
    shell: WIN,
    windowsHide: true,
    ...opts,
  });
  if (opts.allowFail) return result;
  if (result.error) fail(`${command} ${args.join(" ")}: ${result.error.message}`);
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || "").trim();
    fail(`${command} ${args.join(" ")} failed${detail ? `\n${detail}` : ""}`);
  }
  return (result.stdout || "").trim();
}

function git(args, opts) {
  return run("git", args, opts);
}

function tryGh(args) {
  return run("gh", args, { allowFail: true });
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function parseArgs(argv) {
  const out = {
    dryRun: false,
    dispatch: false,
    watch: false,
    bump: null,
    version: null,
  };
  for (const arg of argv) {
    if (arg === "--dry-run") out.dryRun = true;
    else if (arg === "--dispatch") out.dispatch = true;
    else if (arg === "--watch") out.watch = true;
    else if (arg === "--patch" || arg === "--minor" || arg === "--major") {
      out.bump = arg.slice(2);
    } else if (arg.startsWith("-")) {
      fail(`unknown flag ${arg}`);
    } else if (SEMVER.test(arg)) {
      out.version = arg;
    } else {
      fail(`invalid version '${arg}', expected x.y.z`);
    }
  }
  if (out.bump && out.version) fail("pass either a version or --patch/--minor/--major");
  if (out.dispatch && (out.bump || out.version)) {
    fail("--dispatch cannot bump version; omit it or use npm run release");
  }
  return out;
}

function bumpVersion(current, kind) {
  const parts = current.split(".").map((n) => Number(n));
  if (parts.some((n) => Number.isNaN(n)) || parts.length !== 3) {
    fail(`cannot bump invalid version '${current}'`);
  }
  if (kind === "major") {
    parts[0] += 1;
    parts[1] = 0;
    parts[2] = 0;
  } else if (kind === "minor") {
    parts[1] += 1;
    parts[2] = 0;
  } else {
    parts[2] += 1;
  }
  return parts.join(".");
}

function requireCleanTree(reason) {
  const dirty = git(["status", "--porcelain"]);
  if (!dirty) return;
  const extra = reason ? ` (${reason})` : "";
  fail(`working tree is not clean; commit or stash first${extra}`);
}

function requireGh() {
  const probe = tryGh(["--version"]);
  if (probe.error || probe.status !== 0) {
    fail("GitHub CLI (gh) is required. Install https://cli.github.com/ then run gh auth login");
  }
  const auth = tryGh(["auth", "status"]);
  if (auth.status !== 0) {
    fail("gh is not logged in. Run: gh auth login");
  }
}

function printGhRuns() {
  const gh = tryGh(["run", "list", `--workflow=${WORKFLOW}`, "--limit", "3"]);
  if (gh.status === 0 && gh.stdout) {
    console.log("");
    console.log(gh.stdout.trim());
  }
}

function findNewDispatchRun(branch, startedAtMs) {
  for (let i = 0; i < 20; i++) {
    const gh = tryGh([
      "run",
      "list",
      `--workflow=${WORKFLOW}`,
      "--branch",
      branch,
      "--json",
      "databaseId,status,url,event,createdAt",
      "--limit",
      "5",
    ]);
    if (gh.status === 0 && gh.stdout) {
      try {
        const runs = JSON.parse(gh.stdout);
        const match = runs.find((run) => {
          if (run.event !== "workflow_dispatch") return false;
          const created = Date.parse(run.createdAt);
          return Number.isFinite(created) && created + 5000 >= startedAtMs;
        });
        if (match) return match;
      } catch {
        /* retry */
      }
    }
    sleep(2000);
  }
  return null;
}

function dispatchCloudPackage(branch, watch) {
  requireGh();
  const startedAtMs = Date.now();
  run("gh", ["workflow", "run", WORKFLOW, "--ref", branch], { stdio: "inherit" });
  const runInfo = findNewDispatchRun(branch, startedAtMs);
  const actionsUrl = `https://github.com/${REPO}/actions`;
  console.log("");
  console.log(`CI dispatched on ${branch}`);
  console.log(`  runs: ${runInfo?.url || actionsUrl}`);
  console.log("  artifacts: my-cowork-mac / my-cowork-win");
  console.log(`  release: https://github.com/${REPO}/releases (after the release job finishes)`);
  if (!watch) {
    console.log("  watch:  npm run package:ci -- --watch");
    printGhRuns();
    return;
  }
  if (!runInfo) fail("timed out waiting for the workflow run to appear; check " + actionsUrl);
  run("gh", ["run", "watch", String(runInfo.databaseId), "--exit-status"], {
    stdio: "inherit",
  });
}

function publishReleaseTag(current, next, branch, dryRun) {
  const tag = `v${next}`;
  const localTag = spawnSync("git", ["rev-parse", "-q", "--verify", `refs/tags/${tag}`], {
    cwd: ROOT,
    encoding: "utf8",
    shell: WIN,
    windowsHide: true,
  });
  if (localTag.status === 0) fail(`tag ${tag} already exists locally`);

  const remoteTag = git(["ls-remote", "--tags", "origin", `refs/tags/${tag}`]);
  if (remoteTag) fail(`tag ${tag} already exists on origin`);

  console.log(`branch:  ${branch}`);
  console.log(`version: ${current}${next === current ? "" : ` -> ${next}`}`);
  console.log(`tag:     ${tag}`);
  console.log(`remote:  origin (${REPO})`);

  if (dryRun) {
    console.log("dry-run: no commit, tag, or push");
    return;
  }

  if (next !== current) {
    run(
      "npm",
      ["version", next, "--no-git-tag-version", "--allow-same-version"],
      { stdio: "inherit" },
    );
    git(["add", "package.json", "package-lock.json"]);
    git(["commit", "-m", `chore: release ${tag}`], { stdio: "inherit" });
  }

  git(["tag", "-a", tag, "-m", tag], { stdio: "inherit" });
  git(["push", "-u", "origin", "HEAD"], { stdio: "inherit" });
  git(["push", "origin", tag], { stdio: "inherit" });

  const actionsUrl = `https://github.com/${REPO}/actions`;
  const releaseUrl = `https://github.com/${REPO}/releases/tag/${tag}`;
  console.log("");
  console.log(`CI started for ${tag}`);
  console.log(`  runs:    ${actionsUrl}`);
  console.log(`  release: ${releaseUrl} (after the release job finishes)`);
  printGhRuns();
  console.log("");
  console.log("watch: gh run watch");
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const pkg = JSON.parse(fs.readFileSync(PKG_PATH, "utf8"));
  const current = pkg.version;
  if (!SEMVER.test(current)) fail(`package.json version '${current}' is not x.y.z`);

  const branch = git(["rev-parse", "--abbrev-ref", "HEAD"]);
  if (!branch || branch === "HEAD") fail("detached HEAD; checkout a branch first");

  if (args.dispatch) {
    console.log(`branch:  ${branch}`);
    console.log(`version: ${current}`);
    console.log("mode:    workflow_dispatch (package + GitHub Release)");
    if (args.dryRun) {
      const dirty = git(["status", "--porcelain"]);
      if (dirty) console.log("warning: working tree is dirty; a real run would refuse");
      console.log("dry-run: no push or workflow_dispatch");
      return;
    }
    requireCleanTree("CI builds the pushed commit");
    git(["push", "-u", "origin", "HEAD"], { stdio: "inherit" });
    dispatchCloudPackage(branch, args.watch);
    return;
  }

  const next = args.version || (args.bump ? bumpVersion(current, args.bump) : current);
  if (args.dryRun) {
    const dirty = git(["status", "--porcelain"]);
    if (dirty) console.log("warning: working tree is dirty; a real run would refuse");
    publishReleaseTag(current, next, branch, true);
    return;
  }
  requireCleanTree(next === current ? "" : "before bumping version");
  publishReleaseTag(current, next, branch, false);
}

main();
