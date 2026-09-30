import io, json, os, uuid
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from .catalog import *
from .engine import calc
from .db import Base, engine, SessionLocal
from .models import Project, SizingResult
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from openpyxl import Workbook

app = FastAPI(title="AI Infrastructure Sizing Engine", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

def db():
    s = SessionLocal()
    try: yield s
    finally: s.close()

class Login(BaseModel):
    username: str
    password: str

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    industry: str = Field(default="General", min_length=1, max_length=120)

class Sizing(BaseModel):
    project_id: str | None = None
    project_name: str = Field(min_length=1, max_length=200)
    use_case: str
    total_users: int = Field(ge=1)
    active_user_pct: float = Field(ge=0.1, le=100)
    transactions_per_user_day: float = Field(gt=0)
    peak_hours: float = Field(gt=0, le=24)
    peak_factor: float = Field(gt=0)
    avg_latency_seconds: float = Field(gt=0)
    complexity: str
    model_id: str
    gpu_id: str
    server_id: str
    cloud_id: str | None = None
    input_tokens: int = Field(ge=1)
    output_tokens: int = Field(ge=1)
    ha: bool = True
    dr: bool = False
    growth_pct: float = Field(ge=0, le=500)
    spare_pct: float = Field(ge=0, le=100)
    years: int = Field(ge=1, le=10)
    validated_tps_per_gpu: float | None = Field(default=None, gt=0)

def utcnow(): return datetime.now(timezone.utc).replace(tzinfo=None)

def result_payload(rid: str, s: SizingResult):
    p = json.loads(s.payload)
    p["result_id"] = rid
    p["project_name"] = s.project_name
    p["created_at"] = s.created_at.isoformat() + "Z"
    return p

@app.get("/health")
def health(db: Session = Depends(db)):
    db.execute(__import__('sqlalchemy').text("SELECT 1"))
    return {"status":"ok","version":"1.0.0","catalog_version":CATALOG_VERSION,"database":"ok"}

@app.post("/auth/login")
def login(x: Login):
    users={os.getenv("ADMIN_USERNAME","admin"):os.getenv("ADMIN_PASSWORD","Admin@12345"), os.getenv("USER_USERNAME","user"):os.getenv("USER_PASSWORD","User@12345")}
    if users.get(x.username)!=x.password: raise HTTPException(401,"Invalid credentials")
    return {"access_token":"local-"+x.username,"username":x.username,"role":"admin" if x.username=="admin" else "user"}

@app.get("/catalog/use-cases")
def use_cases(): return USE_CASES
@app.get("/catalog/models")
def models(): return MODELS
@app.get("/catalog/gpus")
def gpus(): return GPUS
@app.get("/catalog/servers")
def servers(): return SERVERS
@app.get("/catalog/cloud")
def cloud(): return CLOUD
@app.get("/catalog/evidence")
def evidence(): return EVIDENCE
@app.get("/catalog/assumptions")
def assumptions(): return ASSUMPTIONS

@app.get("/projects")
def projects(db: Session = Depends(db)):
    rows = db.query(Project).order_by(Project.created_at.desc()).all()
    return [{"id":p.id,"name":p.name,"industry":p.industry,"created_at":p.created_at.isoformat()+"Z","latest_result_id":p.latest_result_id} for p in rows]

@app.post("/projects")
def create_project(x: ProjectIn, db: Session = Depends(db)):
    pid=str(uuid.uuid4()); p=Project(id=pid,name=x.name,industry=x.industry,created_at=utcnow())
    db.add(p); db.commit(); db.refresh(p)
    return {"id":p.id,"name":p.name,"industry":p.industry,"created_at":p.created_at.isoformat()+"Z","latest_result_id":None}

@app.post("/sizing/calculate")
def calculate(x:Sizing, db: Session = Depends(db)):
    if x.project_id and not db.get(Project, x.project_id): raise HTTPException(404,"Project not found")
    try: result=calc(x.model_dump())
    except ValueError as e: raise HTTPException(400,str(e))
    rid=str(uuid.uuid4()); now=utcnow(); result["result_id"]=rid; result["project_name"]=x.project_name; result["created_at"]=now.isoformat()+"Z"
    row=SizingResult(id=rid,project_id=x.project_id,project_name=x.project_name,created_at=now,payload=json.dumps(result))
    db.add(row)
    if x.project_id:
        p=db.get(Project,x.project_id); p.latest_result_id=rid
    db.commit()
    return result

@app.get("/sizing/{rid}")
def get_result(rid:str, db: Session = Depends(db)):
    row=db.get(SizingResult,rid)
    if not row: raise HTTPException(404,"Result not found")
    return result_payload(rid,row)

@app.get("/projects/{pid}/results")
def project_results(pid:str, db: Session = Depends(db)):
    if not db.get(Project,pid): raise HTTPException(404,"Project not found")
    rows=db.query(SizingResult).filter(SizingResult.project_id==pid).order_by(SizingResult.created_at.desc()).all()
    return [result_payload(r.id,r) for r in rows]

def flatten(r):
    rows=[]
    def walk(prefix,v):
        if isinstance(v,dict):
            for k,x in v.items(): walk(prefix+"."+k if prefix else k,x)
        elif isinstance(v,list): rows.append((prefix,json.dumps(v)))
        else: rows.append((prefix,str(v)))
    walk("",r); return rows

def load_result(rid, db):
    row=db.get(SizingResult,rid)
    if not row: raise HTTPException(404,"Result not found")
    return result_payload(rid,row)

@app.get("/reports/{rid}.json")
def report_json(rid:str, db: Session = Depends(db)): return load_result(rid,db)

@app.get("/reports/{rid}.pdf")
def report_pdf(rid:str, db: Session = Depends(db)):
    r=load_result(rid,db); buf=io.BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=36,leftMargin=36,topMargin=36,bottomMargin=36)
    story=[Paragraph("AI Infrastructure Sizing Engine — Sizing Report"),Spacer(1,12),Paragraph(f"Project: {r['project_name']}"),Paragraph(f"Generated: {r['created_at']}"),Spacer(1,12)]
    data=[["Metric","Value"]]
    for k,v in flatten(r):
        if k.startswith(("workload.","memory.","gpu.","infrastructure.","cost.","resilience.","cloud.")): data.append([k,str(v)])
    t=Table(data,colWidths=[230,290]); t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.4,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("VALIGN",(0,0),(-1,-1),"TOP")]))
    story.append(t); doc.build(story); buf.seek(0)
    return StreamingResponse(buf,media_type="application/pdf",headers={"Content-Disposition":f"attachment; filename=sizing-{rid}.pdf"})

@app.get("/reports/{rid}.xlsx")
def report_xlsx(rid:str, db: Session = Depends(db)):
    r=load_result(rid,db); wb=Workbook(); ws=wb.active; ws.title="Sizing Result"; ws.append(["Metric","Value"])
    for k,v in flatten(r): ws.append([k,v])
    ws2=wb.create_sheet("Evidence"); ws2.append(["Title","URL","Confidence"])
    for e in r["evidence"]: ws2.append([e["title"],e["url"],e["confidence"]])
    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    return StreamingResponse(buf,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f"attachment; filename=sizing-{rid}.xlsx"})
