# commit-with-fx

`fcom` groups changes in the current Git repository by purpose with [fx](https://fx.sh/) and creates separate commits. Requires Python 3, Git, and fx; no Python packages are needed. [Japanese version](docs/README.ja.md)

## Install

```sh
# Add this repository to your PATH
chmod +x fcom fcom-config
export PATH="/path/to/commit-with-fx:$PATH"
```

## Usage

```sh
fcom                    # Group and commit changes in the current repository
fcom-config all         # Default: staged, unstaged, and untracked changes
fcom-config staged      # Staged changes only, for this repository
```

`fcom-config` sets the local Git config key `fcom.scope`. Ignored files are excluded. `fcom` sends the diff to fx in a single request; check for secrets before running it. A loading indicator appears while fx generates the plan.

Before committing, `fcom` displays only each commit name and its target files with added/deleted line counts (`binary` for binary files). It asks for approval **once**; diff contents are not displayed. Names follow Conventional Commits, such as `feat: ...`, `docs: ...`, or `feat(cli): ...`. Enter `y` to commit, `n` to cancel, or `{"1":"fix: new name","2":"docs: another name"}` to edit names and commit. There is no second confirmation. Invalid fx messages stop before any commit; invalid edits cancel the run.

Changes are split by Git diff hunk, so separate changes in one file can become separate commits. If the split cannot be applied or fx fails, the run stops before confirmation. The original staging area stays untouched until approval. After approval, `fcom` creates commits with a temporary index, then syncs the original index with the final commit. Git hooks run as usual. **If a hook or Git command fails partway through, completed commits remain**; check `git status` for the rest. In `all` mode, the final working-tree contents take precedence; if a staged change is fully reversed in the working tree, the tool stops instead of silently dropping it. Use `staged` mode to commit only the staged version.

Tests: `python3 -m unittest discover -s tests -v`
