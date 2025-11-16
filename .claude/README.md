# Claude Code Settings

This directory contains configuration for Claude Code auto-permissions.

## Auto-Granted Permissions

The following operations are automatically approved and won't require manual confirmation:

### Read Operations ✅
- `Read` - Reading files
- `Glob` - Finding files by pattern
- `Grep` - Searching file contents
- `BashOutput` - Reading background command output

### Write Operations ✅
- `Write` - Creating/overwriting files
- `Edit` - Editing existing files
- `NotebookEdit` - Editing Jupyter notebooks

### Package Management ✅
**Node.js:**
- `npm install`, `npm run`, `npm start`, `npm test`, `npm run dev`, `npm run build`
- `yarn`, `pnpm`

**Python:**
- `pip install`, `pip list`, `pip show`
- `poetry`, `pipenv`

### Git Operations ✅
- `git status`, `git log`, `git diff`, `git show`, `git branch`
- `git add`, `git commit`, `git push`, `git pull`, `git fetch`
- `git checkout`, `git stash`, `git remote`
- `gh` (GitHub CLI)

### Safe File Operations ✅
- `ls`, `cat`, `head`, `tail`, `pwd`, `echo`
- `mkdir`, `touch`, `cp`, `mv`

### Development Servers ✅
- `uvicorn` (FastAPI)
- `python`, `node`, `npx`
- `next` (Next.js)
- `tsc`, `eslint`, `prettier`

### Testing & Linting ✅
- `pytest`, `jest`, `vitest`
- `ruff`, `black`, `mypy`

### Search & Utilities ✅
- `find`, `grep`, `rg`, `ag`, `fd`
- `curl`, `wget`, `jq`
- `sed`, `awk`, `sort`, `uniq`, `wc`
- `docker ps`, `docker images`, `docker logs` (read-only)

### Claude Tools ✅
- `WebFetch`, `WebSearch`
- `Task` (AI agents)
- `TodoWrite`
- `AskUserQuestion`

---

## Operations Requiring Confirmation ⚠️

The following operations **require manual approval** for safety:

### Destructive File Operations ⚠️
- `rm` - File deletion
- `rmdir` - Directory deletion

### Destructive Git Operations ⚠️
- `git reset --hard` - Hard reset
- `git push --force` - Force push
- `git clean` - Removing untracked files

### Process Management ⚠️
- `kill`, `pkill`, `killall` - Process termination
- (Note: `KillShell` tool for background processes is safe)

### Docker Destructive Operations ⚠️
- `docker rm` - Container deletion
- `docker rmi` - Image deletion
- `docker system prune` - System cleanup

### System Operations ⚠️
- `chmod`, `chown` - Permission changes
- `sudo` - Superuser operations

---

## Why These Permissions?

**Auto-granted operations are:**
- ✅ Read-only or non-destructive
- ✅ Commonly used in development
- ✅ Easily reversible (like git commits)
- ✅ Safe for collaborative coding

**Confirmation-required operations are:**
- ⚠️ Destructive or irreversible
- ⚠️ Could delete important files
- ⚠️ Could affect system configuration
- ⚠️ Could terminate critical processes

---

## Modifying Permissions

Edit `.claude/settings.local.json` to customize auto-granted permissions.

**Example:** To auto-grant `rm` (not recommended):
```json
{
  "autoGrantPermissions": [
    "Bash(rm:*)"
  ]
}
```

**Restart Claude Code** after modifying settings for changes to take effect.
