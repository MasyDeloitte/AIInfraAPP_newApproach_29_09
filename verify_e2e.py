#!/usr/bin/env python3
"""Black-box verification for the Docker Compose application.
Run after `docker-compose up -d --build` from the package root.
"""
import json, sys, os, urllib.request, urllib.error
BASE = os.getenv("VERIFY_BASE", "http://localhost:8000")
WEB = os.getenv("VERIFY_WEB", "http://localhost:3000")

def req(path, method="GET", data=None):
    body = None if data is None else json.dumps(data).encode()
    r = urllib.request.Request(BASE + path, data=body, method=method, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(r, timeout=15) as x:
        return x.status, x.headers, x.read()

def check(name, fn):
    try:
        fn(); print("PASS", name); return True
    except Exception as e:
        print("FAIL", name, "-", e); return False

passed = 0; total = 0
def run(name, fn):
    global passed,total
    total += 1
    if check(name,fn): passed += 1

run("frontend responds", lambda: (_ for _ in ()).throw(Exception("HTTP status not 200")) if urllib.request.urlopen(WEB, timeout=15).status != 200 else None)
health = {}
def health_check():
    global health
    s,_,b=req("/health"); health=json.loads(b)
    assert s==200 and health["status"]=="ok" and health["database"]=="ok"
run("backend health + database", health_check)

def assert_len(path,m):
    s,_,b=req(path); assert s==200 and len(json.loads(b))>=m

for path, minimum in [("/catalog/use-cases",15),("/catalog/models",20),("/catalog/gpus",6),("/catalog/servers",20),("/catalog/cloud",20),("/catalog/evidence",1),("/catalog/assumptions",1)]:
    run("catalog "+path, lambda p=path,m=minimum: assert_len(p,m))

# login
run("login", lambda: (lambda x: (_ for _ in ()).throw(Exception("bad login")) if x[0]!=200 else None)(req("/auth/login","POST",{"username":"admin","password":"Admin@12345"})))
proj={}
def create():
    global proj
    s,_,b=req("/projects","POST",{"name":"E2E Verification Project","industry":"Technology"}); assert s==200; proj=json.loads(b); assert proj["id"]
run("project creation",create)
payload={"project_id":proj["id"],"project_name":proj["name"],"use_case":"llm_inference","total_users":10000,"active_user_pct":15,"transactions_per_user_day":20,"peak_hours":4,"peak_factor":3,"avg_latency_seconds":2,"complexity":"medium","model_id":"llama-3.1-70b","gpu_id":"nvidia-h100-80","server_id":"dell-r760xa-h100","cloud_id":"aws-p5","input_tokens":2000,"output_tokens":500,"ha":True,"dr":False,"growth_pct":30,"spare_pct":10,"years":3,"validated_tps_per_gpu":None}
result={}
def calculate():
    global result
    s,_,b=req("/sizing/calculate","POST",payload); assert s==200; result=json.loads(b); assert result["result_id"]
    assert "Insufficient Evidence" in result["gpu"]["performance_basis"]
    assert result["cost"]["price_status"]=="Estimated Price"
run("deterministic sizing",calculate)
rid=result.get("result_id","")
run("saved result",lambda: (lambda x: (_ for _ in ()).throw(Exception("not saved")) if x[0]!=200 or json.loads(x[2])["result_id"]!=rid else None)(req("/sizing/"+rid)))
run("project latest result",lambda: (lambda x: (_ for _ in ()).throw(Exception("latest result missing")) if not any(p["id"]==proj["id"] and p["latest_result_id"]==rid for p in json.loads(x[2])) else None)(req("/projects")))
for ext,ct in [("json","application/json"),("pdf","application/pdf"),("xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]:
    run("report "+ext,lambda e=ext,c=ct: (lambda x: (_ for _ in ()).throw(Exception("bad report")) if x[0]!=200 or not x[1].get_content_type().startswith(c.split(';')[0]) else None)(req("/reports/"+rid+"."+e)))
print(f"\n{passed}/{total} checks passed")
if passed != total: sys.exit(1)
