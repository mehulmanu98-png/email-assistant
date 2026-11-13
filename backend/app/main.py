from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, desc, func
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db, init_db
from .models import User, EmailAccount, EmailMessage, ReplyDraft, FollowUp, AITask, AIConversation, SyncJob, utcnow
from .security import hash_password, verify_password, create_access_token, current_user, get_fernet, COOKIE_NAME
from .schemas import LoginIn, AccountIn, TaskIn, TaskPriorityIn, FollowUpIn, DraftIn, ConversationIn, MessageIn
from .policy import effective_priority

app=FastAPI(title=settings.app_name,version="0.1.0")
app.add_middleware(CORSMiddleware,allow_origins=[settings.frontend_origin],allow_credentials=True,
                   allow_methods=["GET","POST","PATCH","DELETE"],allow_headers=["Content-Type"])

@app.middleware("http")
async def origin_guard(request:Request,call_next):
    if request.method in {"POST","PATCH","DELETE","PUT"}:
        origin=request.headers.get("origin")
        if origin and origin.rstrip("/")!=settings.frontend_origin.rstrip("/"):
            return Response("Origin not allowed",status_code=403)
    return await call_next(request)

@app.on_event("startup")
def startup():
    if settings.app_env=="production":
        if settings.jwt_secret=="development-only-change-this-secret" or len(settings.jwt_secret)<32:
            raise RuntimeError("Production requires a random JWT_SECRET of at least 32 characters.")
        if len(settings.field_encryption_key)<24:
            raise RuntimeError("Production requires a dedicated FIELD_ENCRYPTION_KEY seed.")
        if len(settings.bootstrap_password)<12:
            raise RuntimeError("BOOTSTRAP_PASSWORD must contain at least 12 characters.")
    init_db()
    db=next(get_db())
    try:
        if not db.scalar(select(User).limit(1)):
            db.add(User(email=settings.bootstrap_email.lower(),password_hash=hash_password(settings.bootstrap_password)))
            db.commit()
    finally:
        db.close()

@app.get("/api/health")
def health():
    return {"status":"ok","ai_ready":False,"mail_providers":{"icloud":"limited_imap_starter","gmail":"not_configured"},
            "message":"AI inference and scheduled background tasks remain disabled pending the eligible ChatGPT-plan integration."}

@app.post("/api/auth/login")
def login(data:LoginIn,response:Response,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==data.email.lower()))
    if not user or not verify_password(data.password,user.password_hash):
        raise HTTPException(401,"Invalid email or password")
    response.set_cookie(COOKIE_NAME,create_access_token(user.id),httponly=True,secure=settings.app_env=="production",
                        samesite="strict",max_age=43200,path="/")
    return {"email":user.email}

@app.post("/api/auth/logout")
def logout(response:Response):
    response.delete_cookie(COOKIE_NAME,path="/",httponly=True,samesite="strict")
    return {"ok":True}

@app.get("/api/auth/me")
def me(user:User=Depends(current_user)):
    return {"id":user.id,"email":user.email}

@app.get("/api/dashboard")
def dashboard(user:User=Depends(current_user),db:Session=Depends(get_db)):
    def count(model,*criteria):
        return db.scalar(select(func.count()).select_from(model).where(*criteria)) or 0
    return {"accounts":count(EmailAccount,EmailAccount.user_id==user.id),
            "unread":count(EmailMessage,EmailMessage.user_id==user.id,EmailMessage.is_read.is_(False),EmailMessage.is_trashed.is_(False)),
            "followups":count(FollowUp,FollowUp.user_id==user.id,FollowUp.status.in_(["action_required","awaiting_response"])),
            "active_tasks":count(AITask,AITask.user_id==user.id,AITask.status.in_(["queued","in_progress","waiting_for_user"])),
            "ai_ready":False}

@app.get("/api/accounts")
def accounts(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(EmailAccount).where(EmailAccount.user_id==user.id).order_by(EmailAccount.id)).all()
    return [{"id":a.id,"provider":a.provider,"email":a.email,"status":a.connection_status,"last_sync_at":a.last_sync_at} for a in rows]

@app.post("/api/accounts")
def add_account(data:AccountIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    address=data.email.lower()
    if db.scalar(select(EmailAccount).where(EmailAccount.user_id==user.id,EmailAccount.email==address)):
        raise HTTPException(409,"Account already connected.")
    if data.provider=="gmail":
        raise HTTPException(501,"Gmail OAuth is not implemented. Never enter your Google password.")
    if not data.app_password: raise HTTPException(422,"Apple app-specific password required.")
    account=EmailAccount(user_id=user.id,provider="icloud",email=address,
        encrypted_secret=get_fernet().encrypt(data.app_password.encode()).decode(),connection_status="pending_verification")
    db.add(account);db.commit();db.refresh(account)
    db.add(SyncJob(user_id=user.id,account_id=account.id,status="queued",details="Limited 90-day Inbox import"))
    db.commit()
    return {"id":account.id,"status":"verification_queued"}

@app.delete("/api/accounts/{account_id}")
def disconnect_account(account_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    account=db.scalar(select(EmailAccount).where(EmailAccount.id==account_id,EmailAccount.user_id==user.id))
    if not account:raise HTTPException(404,"Account not found")
    account.encrypted_secret=None;account.connection_status="disconnected";db.commit()
    return {"status":"disconnected","history_retained":True}

@app.post("/api/sync")
def sync_all(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(EmailAccount).where(EmailAccount.user_id==user.id,EmailAccount.provider=="icloud",EmailAccount.connection_status!="disconnected")).all()
    for a in rows:db.add(SyncJob(user_id=user.id,account_id=a.id,status="queued",details="Manual sync"))
    db.commit()
    return {"queued":len(rows)}

@app.post("/api/sync/{account_id}")
def sync_one(account_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    a=db.scalar(select(EmailAccount).where(EmailAccount.id==account_id,EmailAccount.user_id==user.id))
    if not a:raise HTTPException(404,"Account not found")
    if a.provider!="icloud":raise HTTPException(501,"Provider adapter unavailable.")
    db.add(SyncJob(user_id=user.id,account_id=a.id,status="queued",details="Manual sync"));db.commit()
    return {"queued":True}

@app.get("/api/sync/jobs")
def sync_jobs(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(SyncJob).where(SyncJob.user_id==user.id).order_by(desc(SyncJob.id)).limit(30)).all()
    return [{"id":x.id,"account_id":x.account_id,"status":x.status,"details":x.details,"created_at":x.created_at} for x in rows]

@app.get("/api/messages")
def messages(q:str="",account_id:int|None=None,unread:bool=False,user:User=Depends(current_user),db:Session=Depends(get_db)):
    stmt=select(EmailMessage).where(EmailMessage.user_id==user.id,EmailMessage.is_trashed.is_(False))
    if account_id:stmt=stmt.where(EmailMessage.account_id==account_id)
    if unread:stmt=stmt.where(EmailMessage.is_read.is_(False))
    if q:stmt=stmt.where(EmailMessage.subject.ilike("%"+q+"%")|EmailMessage.sender.ilike("%"+q+"%")|EmailMessage.body_text.ilike("%"+q+"%"))
    rows=db.scalars(stmt.order_by(desc(EmailMessage.received_at),desc(EmailMessage.id)).limit(200)).all()
    return [{"id":x.id,"account_id":x.account_id,"sender":x.sender,"recipients":x.recipients,"subject":x.subject,
        "received_at":x.received_at,"snippet":x.snippet,"summary":x.current_summary,"thread_summary":x.thread_summary,
        "priority":x.priority,"priority_reason":x.priority_reason,"is_read":x.is_read,"has_attachments":x.has_attachments} for x in rows]

@app.get("/api/messages/{message_id}")
def message_detail(message_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    x=db.scalar(select(EmailMessage).where(EmailMessage.id==message_id,EmailMessage.user_id==user.id))
    if not x or x.is_trashed:raise HTTPException(404,"Email not found")
    a=db.get(EmailAccount,x.account_id)
    return {"id":x.id,"account_id":x.account_id,"account_email":a.email if a else "","sender":x.sender,
        "recipients":x.recipients,"subject":x.subject,"received_at":x.received_at,"body_text":x.body_text,
        "summary":x.current_summary,"thread_summary":x.thread_summary,"is_read":x.is_read,"has_attachments":x.has_attachments}

@app.post("/api/messages/{message_id}/read")
def mark_read(message_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    x=db.scalar(select(EmailMessage).where(EmailMessage.id==message_id,EmailMessage.user_id==user.id))
    if not x:raise HTTPException(404,"Email not found")
    x.is_read=True;db.commit()
    return {"is_read":True,"provider_sync":"not_confirmed","note":"Local state only; provider write-back has not been implemented."}

@app.delete("/api/messages/{message_id}")
def delete_message(message_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    if not db.scalar(select(EmailMessage).where(EmailMessage.id==message_id,EmailMessage.user_id==user.id)):
        raise HTTPException(404,"Email not found")
    raise HTTPException(501,"Provider-side move to Trash is not implemented; nothing was deleted.")

def draft_out(d):
    return {"id":d.id,"message_id":d.message_id,"to":d.to_json,"cc":d.cc_json,"bcc":d.bcc_json,"subject":d.subject,"body":d.body,"status":d.status}

@app.post("/api/messages/{message_id}/draft")
def create_draft(message_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    msg=db.scalar(select(EmailMessage).where(EmailMessage.id==message_id,EmailMessage.user_id==user.id))
    if not msg:raise HTTPException(404,"Email not found")
    draft=db.scalar(select(ReplyDraft).where(ReplyDraft.message_id==message_id,ReplyDraft.user_id==user.id))
    if not draft:
        subject=msg.subject if msg.subject.lower().startswith("re:") else "Re: "+msg.subject
        draft=ReplyDraft(user_id=user.id,message_id=msg.id,to_json=[msg.sender],subject=subject)
        db.add(draft);db.commit();db.refresh(draft)
    return draft_out(draft)

@app.patch("/api/drafts/{draft_id}")
def save_draft(draft_id:int,data:DraftIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    d=db.scalar(select(ReplyDraft).where(ReplyDraft.id==draft_id,ReplyDraft.user_id==user.id))
    if not d:raise HTTPException(404,"Draft not found")
    d.to_json=[str(v) for v in data.to];d.cc_json=[str(v) for v in data.cc];d.bcc_json=[str(v) for v in data.bcc]
    d.subject=data.subject;d.body=data.body;db.commit()
    return draft_out(d)

@app.post("/api/drafts/{draft_id}/send")
def send_draft(draft_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    if not db.scalar(select(ReplyDraft).where(ReplyDraft.id==draft_id,ReplyDraft.user_id==user.id)):
        raise HTTPException(404,"Draft not found")
    raise HTTPException(501,"Sending is disabled until approval snapshots, source-account enforcement and duplicate-send safeguards are implemented.")

@app.get("/api/followups")
def followups(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(FollowUp).where(FollowUp.user_id==user.id,FollowUp.status.in_(["action_required","awaiting_response"])).order_by(FollowUp.due_at)).all()
    return [{"id":x.id,"title":x.title,"description":x.description,"owner":x.owner,"due_at":x.due_at,"status":x.status,"message_id":x.message_id} for x in rows]

@app.post("/api/followups")
def add_followup(data:FollowUpIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    if data.message_id and not db.scalar(select(EmailMessage).where(EmailMessage.id==data.message_id,EmailMessage.user_id==user.id)):
        raise HTTPException(404,"Source email not found")
    x=FollowUp(user_id=user.id,**data.model_dump());db.add(x);db.commit();db.refresh(x)
    return {"id":x.id,"title":x.title,"description":x.description,"owner":x.owner,"due_at":x.due_at,"status":x.status,"message_id":x.message_id}

@app.patch("/api/followups/{followup_id}/complete")
def complete_followup(followup_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    x=db.scalar(select(FollowUp).where(FollowUp.id==followup_id,FollowUp.user_id==user.id))
    if not x:raise HTTPException(404,"Follow-up not found")
    x.status="completed";db.commit();return {"completed":True}

@app.delete("/api/followups/{followup_id}")
def remove_followup(followup_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    x=db.scalar(select(FollowUp).where(FollowUp.id==followup_id,FollowUp.user_id==user.id))
    if not x:raise HTTPException(404,"Follow-up not found")
    db.delete(x);db.commit();return {"removed":True,"email_retained":True}

@app.get("/api/tasks")
def tasks(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(AITask).where(AITask.user_id==user.id).order_by(desc(AITask.created_at))).all()
    return [task_out(x) for x in rows]

def task_out(x):
    return {"id":x.id,"title":x.title,"instructions":x.instructions,"status":x.status,"priority":x.effective_priority,
        "base_priority":x.base_priority,"priority_override_by_user":x.priority_override_by_user,
        "deadline_type":x.deadline_type,"deadline_at":x.deadline_at,"scheduled_start_at":x.scheduled_start_at,
        "reason":x.priority_reason,"blocker":x.execution_blocker,"created_at":x.created_at}

@app.post("/api/tasks")
def add_task(data:TaskIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=effective_priority(data.priority,data.deadline_at,data.deadline_type,False)
    x=AITask(user_id=user.id,title=data.title,instructions=data.instructions,base_priority=data.priority,effective_priority=p,
        deadline_type=data.deadline_type,deadline_at=data.deadline_at,scheduled_start_at=data.scheduled_start_at,
        priority_reason="Calculated from base priority and deadline rules.",
        execution_blocker="AI execution is paused until an eligible ChatGPT-plan runtime is implemented and configured.")
    db.add(x);db.commit();db.refresh(x);return task_out(x)

@app.patch("/api/tasks/{task_id}/priority")
def set_priority(task_id:int,data:TaskPriorityIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    x=db.scalar(select(AITask).where(AITask.id==task_id,AITask.user_id==user.id))
    if not x:raise HTTPException(404,"Task not found")
    if data.automatic:
        x.priority_override_by_user=False
        x.effective_priority=effective_priority(x.base_priority,x.deadline_at,x.deadline_type,False)
    else:
        if not data.priority:raise HTTPException(422,"Select a priority or reset to Automatic.")
        x.base_priority=data.priority;x.effective_priority=data.priority;x.priority_override_by_user=True;x.priority_reason="Manually set by user."
    db.commit();return task_out(x)

@app.patch("/api/tasks/{task_id}/cancel")
def cancel_task(task_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    x=db.scalar(select(AITask).where(AITask.id==task_id,AITask.user_id==user.id))
    if not x:raise HTTPException(404,"Task not found")
    x.status="cancelled";db.commit();return task_out(x)

@app.get("/api/conversations")
def conversations(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(AIConversation).where(AIConversation.user_id==user.id).order_by(desc(AIConversation.updated_at))).all()
    return [{"id":x.id,"title":x.title,"updated_at":x.updated_at} for x in rows]

@app.post("/api/conversations")
def create_conversation(data:ConversationIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    x=AIConversation(user_id=user.id,title=data.title,messages=[]);db.add(x);db.commit();db.refresh(x)
    return {"id":x.id,"title":x.title,"messages":x.messages}

@app.get("/api/conversations/{conversation_id}")
def conversation_detail(conversation_id:int,user:User=Depends(current_user),db:Session=Depends(get_db)):
    x=db.scalar(select(AIConversation).where(AIConversation.id==conversation_id,AIConversation.user_id==user.id))
    if not x:raise HTTPException(404,"Conversation not found")
    return {"id":x.id,"title":x.title,"messages":x.messages}

@app.post("/api/conversations/{conversation_id}/messages")
def conversation_message(conversation_id:int,data:MessageIn,user:User=Depends(current_user),db:Session=Depends(get_db)):
    x=db.scalar(select(AIConversation).where(AIConversation.id==conversation_id,AIConversation.user_id==user.id))
    if not x:raise HTTPException(404,"Conversation not found")
    history=list(x.messages or [])
    history.append({"role":"user","content":data.content,"at":utcnow().isoformat()})
    history.append({"role":"system","content":"Message saved, but AI replies are paused. No paid API fallback is configured.","at":utcnow().isoformat()})
    x.messages=history;db.commit()
    raise HTTPException(503,"Your message was saved. AI responses are paused until the official ChatGPT-plan integration is implemented and connected.")
