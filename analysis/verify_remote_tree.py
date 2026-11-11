import sys, json, subprocess, urllib.request
sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
from dynamic_credentials import add_surrogate_to_request
API = "https://api.github.com"
def api(path):
    req = urllib.request.Request(API + path, headers={"Accept": "application/vnd.github+json"})
    add_surrogate_to_request(req, "custom.github", entry_name="access_token", allowed_hosts=("api.github.com",))
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)
commit = api("/repos/jurayh/sluice/commits/main")
print("remote commit:", commit["sha"], commit["commit"]["message"].splitlines()[0])
tree = api(f"/repos/jurayh/sluice/git/trees/{commit['sha']}?recursive=1")
remote = {t["path"]: t["sha"] for t in tree["tree"] if t["type"] == "blob"}
print("remote blobs:", len(remote))
out = subprocess.run(["git", "ls-files"], cwd="/home/hatch/workspace/sluice",
                     capture_output=True, text=True, check=True).stdout.splitlines()
mismatch = []
for path in out:
    h = subprocess.run(["git", "hash-object", path], cwd="/home/hatch/workspace/sluice",
                       capture_output=True, text=True, check=True).stdout.strip()
    if remote.get(path) != h:
        mismatch.append((path, h, remote.get(path)))
print("local tracked:", len(out), "mismatches:", mismatch if mismatch else "none")
extra = sorted(set(remote) - set(out))
print("remote-only files:", extra if extra else "none")
