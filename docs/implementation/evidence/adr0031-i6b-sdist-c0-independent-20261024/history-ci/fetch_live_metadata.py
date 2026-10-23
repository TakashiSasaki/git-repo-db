"""Read-only supplementary REST metadata not exposed fully by connector wrappers."""
import datetime
import json
import pathlib
import subprocess

HERE=pathlib.Path(__file__).resolve().parent
REPO="repos/TakashiSasaki/git-repo-db/"

def api(path):
    p=subprocess.run(["gh","api",REPO+path],capture_output=True)
    if p.returncode:
        raise RuntimeError((path,p.returncode,p.stderr.decode()))
    return json.loads(p.stdout)

def main():
    d={"observed_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"main":api("git/ref/heads/main"),"pulls":[],"reviews":{},"runs":{},"artifacts":{}}
    for page in range(1,20):
        pulls=api(f"pulls?state=open&per_page=100&page={page}")
        d["pulls"].extend({k:p[k] for k in ("number","title","state","draft","head","base","html_url","updated_at")} for p in pulls)
        if len(pulls)<100:break
    for n in (144,147,149,150,152,153,154,155):
        d["reviews"][str(n)]=api(f"pulls/{n}/reviews?per_page=100")
    for run in (40006927076,40006927148,40006927071):
        raw=api(f"actions/runs/{run}")
        d["runs"][str(run)]={k:raw[k] for k in ("id","name","head_sha","head_branch","event","status","conclusion","run_attempt","path","html_url","created_at","updated_at","pull_requests")}
        # Metadata only. No binary artifact download is attempted after inherited Forbidden.
        d["artifacts"][str(run)]=api(f"actions/runs/{run}/artifacts?per_page=100")
    (HERE/"raw/live-rest-metadata.json").write_text(json.dumps(d,indent=2)+"\n")
    print(json.dumps({"observed_at":d["observed_at"],"main":d["main"]["object"]["sha"],"open_pulls":len(d["pulls"]),"reviews155":len(d["reviews"]["155"]),"runs":d["runs"]},indent=2))

if __name__=="__main__":main()
