# KLERK «کلرک»: deployment repository

Patient records for one private clinic (Persian, right to left, Jalali dates). Each folder named with a date and time
is one published release. Earlier folders are never changed.

**Use the newest folder: `2026-11-13_15-46`.** On a server:

```
git clone https://github.com/MMACABRE/KLERK.git /opt/clinic        # first time; later: git -C /opt/clinic pull --ff-only
newest=$(ls -d /opt/clinic/20*_*/ | sort | tail -1); newest=${newest%/}; echo "$newest"
```

Then follow `$newest/docs/SETUP.md` (a person) or `$newest/docs/DEPLOY-AGENT.md` (a Claude Code session on the
server). A server that runs the old app moves only with `$newest/docs/DEPLOY-AGENT-CUTOVER.md`, on the owner's word.

Folders with `backend/` and `deploy/images.lock` are the new app (Django, MySQL, Vue) and need no build on the
server. Folders with `backend/` but no `images.lock` build on the server (needs Docker Hub, PyPI, npm). Folders
without `backend/` are the old app (Node, SQLite).
