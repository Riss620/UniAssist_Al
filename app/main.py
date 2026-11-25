import os, io, re, hashlib
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv
load_dotenv()
from .db import connect, init_db
from .security import hash_password, verify_password, issue_session, current_user, revoke_session
from .agents import ai_reply

@asynccontextmanager
async def lifespan(app):
    init_db(); yield
app=FastAPI(title='UniAssist AI',version='2.0.0',lifespan=lifespan)
STATIC=Path(__file__).parent/'static'
app.mount('/static',StaticFiles(directory=STATIC),name='static')
class RegisterIn(BaseModel): name:str; email:EmailStr; password:str
class LoginIn(BaseModel): email:EmailStr; password:str
class ChatIn(BaseModel): message:str
class TaskIn(BaseModel): title:str; due_date:str|None=None

@app.get('/')
def home(): return FileResponse(STATIC/'index.html')
@app.get('/health')
def health():
    has_gemini = bool(os.getenv('GEMINI_API_KEY'))
    has_openai = bool(os.getenv('AZURE_OPENAI_ENDPOINT') or os.getenv('OPENAI_BASE_URL')) and bool(os.getenv('AZURE_OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')) and bool(os.getenv('AZURE_OPENAI_DEPLOYMENT') or os.getenv('OPENAI_MODEL'))
    configured = has_gemini or has_openai
    provider = 'gemini' if has_gemini else ('openai/azure' if has_openai else 'none')
    return {'status':'ok','version':'2.0.0','ai_configured':configured,'provider':provider,'mode':'live-capable' if configured else 'local-fallback'}
@app.post('/api/register')
def register(x:RegisterIn):
    if len(x.password)<8: raise HTTPException(400,'Password must be at least 8 characters')
    with connect() as c:
        try: cur=c.execute('INSERT INTO users(name,email,password_hash) VALUES(?,?,?)',(x.name.strip(),x.email.lower(),hash_password(x.password))); uid=cur.lastrowid
        except Exception: raise HTTPException(409,'An account with this email already exists')
    return {'token':issue_session(uid),'user':{'id':uid,'name':x.name,'email':x.email,'role':'student'}}
@app.post('/api/login')
def login(x:LoginIn):
    with connect() as c: row=c.execute('SELECT * FROM users WHERE email=?',(x.email.lower(),)).fetchone()
    if not row or not verify_password(x.password,row['password_hash']): raise HTTPException(401,'Incorrect email or password')
    return {'token':issue_session(row['id']),'user':{'id':row['id'],'name':row['name'],'email':row['email'],'role':row['role']}}
@app.post('/api/logout')
def logout(authorization:str|None=Header(default=None),user=Depends(current_user)):
    revoke_session(authorization); return {'ok':True}
@app.get('/api/me')
def me(user=Depends(current_user)): return user
@app.get('/api/history')
def history(user=Depends(current_user)):
    with connect() as c: rows=c.execute('SELECT role,content,agent,created_at FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 60',(user['id'],)).fetchall()
    return {'messages':[dict(x) for x in reversed(rows)]}
@app.post('/api/chat')
async def chat(x:ChatIn,user=Depends(current_user)):
    q=x.message.strip()
    if not q or len(q)>5000: raise HTTPException(400,'Message must contain 1–5000 characters')
    with connect() as c:
        docs=[dict(r) for r in c.execute('SELECT filename,content FROM documents WHERE user_id=? ORDER BY id DESC LIMIT 20',(user['id'],)).fetchall()]
        hist=c.execute('SELECT role,content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 8',(user['id'],)).fetchall()
        history=[{'role':r['role'],'content':r['content']} for r in reversed(hist) if r['role'] in ('user','assistant')]
    agent,answer,mode=await ai_reply(q,history,docs)
    with connect() as c:
        c.execute('INSERT INTO messages(user_id,role,content,agent) VALUES(?,?,?,?)',(user['id'],'user',q,agent))
        c.execute('INSERT INTO messages(user_id,role,content,agent) VALUES(?,?,?,?)',(user['id'],'assistant',answer,agent))
    return {'answer':answer,'agent':agent,'mode':mode}
@app.post('/api/documents')
async def upload_document(file:UploadFile=File(...),user=Depends(current_user)):
    if not file.filename.lower().endswith('.pdf'): raise HTTPException(400,'Only PDF files are supported')
    raw=await file.read()
    if len(raw)>10*1024*1024: raise HTTPException(413,'PDF must be smaller than 10 MB')
    try:
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(raw)); content='\n'.join((p.extract_text() or '') for p in reader.pages)
    except Exception: raise HTTPException(400,'Could not read this PDF')
    if not content.strip(): raise HTTPException(400,'No selectable text found in this PDF')
    with connect() as c: cur=c.execute('INSERT INTO documents(user_id,filename,content) VALUES(?,?,?)',(user['id'],Path(file.filename).name,content[:250000]))
    return {'id':cur.lastrowid,'filename':Path(file.filename).name,'characters':len(content)}
@app.get('/api/documents')
def documents(user=Depends(current_user)):
    with connect() as c: rows=c.execute('SELECT id,filename,created_at,length(content) AS characters FROM documents WHERE user_id=? ORDER BY id DESC',(user['id'],)).fetchall()
    return {'documents':[dict(r) for r in rows]}
@app.delete('/api/documents/{doc_id}')
def delete_document(doc_id:int,user=Depends(current_user)):
    with connect() as c: cur=c.execute('DELETE FROM documents WHERE id=? AND user_id=?',(doc_id,user['id']))
    if not cur.rowcount: raise HTTPException(404,'Document not found')
    return {'ok':True}
@app.get('/api/tasks')
def tasks(user=Depends(current_user)):
    with connect() as c: rows=c.execute('SELECT * FROM tasks WHERE user_id=? ORDER BY done,due_date,id DESC',(user['id'],)).fetchall()
    return {'tasks':[dict(r) for r in rows]}
@app.post('/api/tasks')
def add_task(x:TaskIn,user=Depends(current_user)):
    if not x.title.strip(): raise HTTPException(400,'Task title is required')
    with connect() as c: cur=c.execute('INSERT INTO tasks(user_id,title,due_date) VALUES(?,?,?)',(user['id'],x.title.strip(),x.due_date))
    return {'id':cur.lastrowid,'title':x.title,'due_date':x.due_date,'done':0}
@app.patch('/api/tasks/{task_id}')
def toggle_task(task_id:int,user=Depends(current_user)):
    with connect() as c:
        row=c.execute('SELECT done FROM tasks WHERE id=? AND user_id=?',(task_id,user['id'])).fetchone()
        if not row: raise HTTPException(404,'Task not found')
        done=1-int(row['done']); c.execute('UPDATE tasks SET done=? WHERE id=? AND user_id=?',(done,task_id,user['id']))
    return {'id':task_id,'done':done}
