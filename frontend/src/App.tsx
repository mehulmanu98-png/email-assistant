import React, {useCallback,useEffect,useState} from "react";
import type {FormEvent,ReactNode} from "react";
import {Inbox,ListChecks,MessageSquare,Settings,Search,RefreshCw,Plus,Mail,AlertCircle,Check,LogOut,Lock,Send,Trash2,Flag,X,Paperclip,ShieldCheck,CalendarClock,CircleDashed,ChevronRight,FileText,ExternalLink,Clock} from "lucide-react";
import {api} from "./api";

type View="Inbox"|"Follow-ups"|"AI Assistant"|"Accounts & Settings";
const nav:{name:View;icon:typeof Inbox}[]=[
 {name:"Inbox",icon:Inbox},{name:"Follow-ups",icon:ListChecks},{name:"AI Assistant",icon:MessageSquare},{name:"Accounts & Settings",icon:Settings}
];
function Empty({icon:Icon=Mail,title,detail,action}:{icon?:typeof Mail;title:string;detail:string;action?:ReactNode}){
 return <div className="empty"><Icon size={28}/><strong>{title}</strong><span>{detail}</span>{action}</div>;
}
function Login({onLogin}:{onLogin:(email:string,password:string)=>Promise<void>}){
 const [email,setEmail]=useState("");const [password,setPassword]=useState("");const [error,setError]=useState("");const [busy,setBusy]=useState(false);
 return <div className="login-page"><form className="login-card" onSubmit={async e=>{e.preventDefault();setBusy(true);setError("");try{await onLogin(email,password)}catch(err){setError(err instanceof Error?err.message:"Sign-in failed")}finally{setBusy(false)}}}>
  <div className="mark big">M</div><h1>Email Assistant</h1><p>Your private email workspace</p>
  <label>Email address</label><input type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} required/>
  <label>Password</label><input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/>
  <button className="button primary full" disabled={busy}>{busy?"Signing in…":"Sign in"}</button>
  {error&&<div className="error">{error}</div>}<small className="secure-caption"><Lock size={13}/> Private single-user access</small>
 </form></div>;
}
export default function App(){
 const [user,setUser]=useState<any>(null),[view,setView]=useState<View>("Inbox");
 const [messages,setMessages]=useState<any[]>([]),[accounts,setAccounts]=useState<any[]>([]),[followups,setFollowups]=useState<any[]>([]),[tasks,setTasks]=useState<any[]>([]);
 const [selected,setSelected]=useState<any>(null),[search,setSearch]=useState(""),[notice,setNotice]=useState(""),[busy,setBusy]=useState(false);
 const [showAccount,setShowAccount]=useState(false),[provider,setProvider]=useState("icloud"),[newEmail,setNewEmail]=useState(""),[appPassword,setAppPassword]=useState("");
 const [taskTitle,setTaskTitle]=useState(""),[taskText,setTaskText]=useState(""),[taskPriority,setTaskPriority]=useState("normal"),[deadline,setDeadline]=useState(""),[deadlineType,setDeadlineType]=useState("target");
 const [conversations,setConversations]=useState<any[]>([]),[conversation,setConversation]=useState<any>(null),[chatInput,setChatInput]=useState("");
 const [draft,setDraft]=useState<any>(null);
 const refresh=useCallback(async()=>{
  setBusy(true);
  try{const [m,a,f,t,c]=await Promise.all([api.messages(search),api.accounts(),api.followups(),api.tasks(),api.conversations()]);
   setMessages(m);setAccounts(a);setFollowups(f);setTasks(t);setConversations(c);
  }catch(err){setNotice(err instanceof Error?err.message:"Refresh failed")}finally{setBusy(false)}
 },[search]);
 useEffect(()=>{api.me().then(setUser).catch(()=>setUser(false))},[]);
 useEffect(()=>{if(user)refresh()},[user,refresh]);
 const login=async(email:string,password:string)=>setUser(await api.login(email,password));
 const openMessage=async(m:any)=>{try{const full=await api.message(m.id);setSelected(full);setDraft(null);await api.markRead(m.id);setMessages(rows=>rows.map(x=>x.id===m.id?{...x,is_read:true}:x))}catch(err){setNotice(String(err))}};
 const sync=async()=>{try{const r=await api.sync();setNotice(r.queued?String(r.queued)+" sync job(s) queued.":"No connected iCloud accounts to sync.")}catch(err){setNotice(String(err))}};
 const connect=async(e:FormEvent)=>{e.preventDefault();try{await api.addAccount(provider,newEmail,appPassword);setShowAccount(false);setNewEmail("");setAppPassword("");setNotice("Account saved. Verification is queued for the cloud worker.");await refresh()}catch(err){setNotice(String(err))}};
 const addTask=async(e:FormEvent)=>{e.preventDefault();try{await api.addTask({title:taskTitle,instructions:taskText,priority:taskPriority,deadline_type:deadline?deadlineType:null,deadline_at:deadline?new Date(deadline).toISOString():null});setTaskTitle("");setTaskText("");setDeadline("");setNotice("Task saved. AI execution is paused until an eligible ChatGPT-plan connection is implemented.");await refresh()}catch(err){setNotice(String(err))}};
 const createConversation=async()=>{try{const c=await api.newConversation("New conversation");setConversation(c);await refresh()}catch(err){setNotice(String(err))}};
 const selectConversation=async(id:number)=>{try{setConversation(await api.conversation(id))}catch(err){setNotice(String(err))}};
 const sendChat=async(e:FormEvent)=>{e.preventDefault();if(!conversation||!chatInput.trim())return;const content=chatInput;setChatInput("");try{await api.sendMessage(conversation.id,content)}catch(err){setNotice(err instanceof Error?err.message:"AI response unavailable")}finally{await selectConversation(conversation.id)}};
 const createDraft=async()=>{if(!selected)return;try{setDraft(await api.createDraft(selected.id));setNotice("Internal draft created. Sending is not enabled in this release.")}catch(err){setNotice(String(err))}};
 const saveDraft=async()=>{if(!draft)return;try{setDraft(await api.saveDraft(draft.id,draft));setNotice("Internal draft saved.")}catch(err){setNotice(String(err))}};
 const sendDraft=async()=>{if(!draft)return;try{await api.sendDraft(draft.id)}catch(err){setNotice(String(err))}};
 if(user===null)return <div className="splash">Loading private workspace…</div>;
 if(user===false)return <Login onLogin={login}/>;
 const active=tasks.filter(t=>["queued","in_progress","waiting_for_user"].includes(t.status));
 const unread=messages.filter(m=>!m.is_read).length;
 return <div className="app-shell">
  <aside className="sidebar"><div className="brand"><div className="mark">M</div><div><b>Email Assistant</b><small>Private workspace</small></div></div><div className="nav-label">WORKSPACE</div>
   {nav.map(n=><button key={n.name} className={"nav-item "+(view===n.name?"active":"")} onClick={()=>{setView(n.name);setSelected(null)}}><n.icon size={18}/><span>{n.name}</span>{n.name==="Inbox"&&unread>0&&<em>{unread}</em>}</button>)}
   <div className="sidebar-bottom"><div className="privacy-chip"><ShieldCheck size={16}/> Private account</div><button className="nav-item" onClick={async()=>{await api.logout();setUser(false)}}><LogOut size={17}/> Sign out</button><small>{user.email}</small></div>
  </aside>
  <main className="main-area"><header className="topbar"><div><span className="eyebrow">YOUR WORKSPACE</span><h1>{view}</h1></div><div className="top-actions"><span className="connection-state"><CircleDashed size={14}/> AI not connected</span><button className="icon-button" title="Refresh" onClick={refresh}><RefreshCw size={17}/></button><button className="button primary" onClick={sync}><RefreshCw size={15}/> Sync Now</button></div></header>
   {notice&&<div className="notice"><AlertCircle size={16}/><span>{notice}</span><button onClick={()=>setNotice("")} aria-label="Dismiss"><X size={15}/></button></div>}
   {view==="Inbox"&&<section className="inbox-layout"><div className="list-pane"><div className="pane-heading"><div><b>All mail</b><small>{messages.length} messages · {unread} unread</small></div><button className="icon-button" onClick={()=>setShowAccount(true)}><Plus size={18}/></button></div><form className="searchbox" onSubmit={e=>{e.preventDefault();refresh()}}><Search size={16}/><input placeholder="Search sender, subject or content" value={search} onChange={e=>setSearch(e.target.value)}/><button><ChevronRight size={16}/></button></form>
    {busy?<Empty title="Loading inbox" detail="Fetching saved email records…"/>:messages.length===0?<Empty title="Your inbox is ready" detail="Connect an iCloud account to begin." action={<button className="button secondary" onClick={()=>setShowAccount(true)}>Connect account</button>}/>:messages.map(m=><button key={m.id} className={"message-row "+(selected?.id===m.id?"selected ":"")+(m.is_read?"":"unread")} onClick={()=>openMessage(m)}><div className="row-top"><b>{m.sender}</b><small>{m.received_at?new Date(m.received_at).toLocaleDateString():""}</small></div><strong>{m.subject||"(No subject)"}</strong><p>{m.summary||m.snippet||"No preview available"}</p><div className="row-meta"><span className={"priority "+m.priority}>{m.priority}</span>{m.has_attachments&&<Paperclip size={13}/>}</div></button>)}
   </div><div className="detail-pane">{selected?<><div className="detail-head"><div><small>{selected.account_email}</small><h2>{selected.subject||"(No subject)"}</h2><p>{selected.sender} · {selected.received_at?new Date(selected.received_at).toLocaleString():""}</p></div><button className="icon-button" onClick={()=>setSelected(null)}><X size={18}/></button></div>
    <div className="summary-card"><label>THIS EMAIL</label><p>{selected.summary||"No AI summary available yet."}</p></div><div className="summary-card"><label>ENTIRE EMAIL TRAIL</label><p>{selected.thread_summary||"No AI thread summary available yet."}</p></div>
    <div className="original"><label>ORIGINAL EMAIL</label><pre>{selected.body_text||"No plain-text body was imported."}</pre></div>
    {draft&&<div className="draft-editor"><div className="draft-title"><FileText size={16}/> Internal reply draft <span>Not sent</span></div>
     <label>To (comma-separated)</label><input value={(draft.to||[]).join(", ")} onChange={e=>setDraft({...draft,to:e.target.value.split(",").map((v:string)=>v.trim()).filter(Boolean)})}/>
     <label>CC</label><input value={(draft.cc||[]).join(", ")} onChange={e=>setDraft({...draft,cc:e.target.value.split(",").map((v:string)=>v.trim()).filter(Boolean)})}/>
     <label>Subject</label><input value={draft.subject||""} onChange={e=>setDraft({...draft,subject:e.target.value})}/>
     <label>Message</label><textarea rows={7} value={draft.body||""} onChange={e=>setDraft({...draft,body:e.target.value})}/>
     <div className="inline-actions"><button className="button secondary" onClick={saveDraft}>Save draft</button><button className="button secondary" onClick={sendDraft}>Approve &amp; Send</button></div></div>}
    <div className="detail-actions"><button className="button secondary" onClick={createDraft}>Create Reply</button><button className="button secondary" onClick={()=>setNotice("Provider Trash action is not implemented. No email was deleted.")}><Trash2 size={15}/> Delete</button><button className="button secondary" onClick={()=>setNotice("Sender blocking is not implemented.")}><Flag size={15}/> Block user</button><button className="button secondary" onClick={()=>setNotice("Original attachment viewing/download is not implemented.")}><Paperclip size={15}/> Attachments</button><button className="button secondary" onClick={()=>setNotice("Apple Notes and Reminders integration is not implemented.")}><CalendarClock size={15}/> Reminder / Note</button></div>
   </>:<Empty title="Select an email" detail="Summaries, original content and available actions appear here."/>}</div></section>}
   {view==="Follow-ups"&&<section className="content-card"><div className="section-head"><div><h2>Follow-ups</h2><p>Commitments and actions linked to email.</p></div><span className="count-pill">{followups.length} active</span></div>{followups.length===0?<Empty icon={Check} title="No active follow-ups" detail="AI follow-up extraction is not connected yet."/>:followups.map(f=><div className="item-row" key={f.id}><div><b>{f.title}</b><p>{f.description}</p><small>{f.owner||"Owner not specified"} · {f.due_at?new Date(f.due_at).toLocaleString():"No due date"} · {f.status.replaceAll("_"," ")}</small></div><div className="inline-actions"><button className="button secondary compact" onClick={async()=>{await api.completeFollowup(f.id);await refresh()}}>Complete</button><button className="icon-button" title="Remove from Follow-ups" onClick={async()=>{await api.removeFollowup(f.id);await refresh()}}><X size={16}/></button></div></div>)}</section>}
   {view==="AI Assistant"&&<section className="assistant-layout"><div className="chat-panel"><div className="section-head"><div><h2>AI Assistant</h2><p>Persistent Email Assistant conversations · separate from ChatGPT history</p></div><button className="button secondary" onClick={createConversation}><Plus size={15}/> New chat</button></div>
    <div className="conversation-strip">{conversations.map(c=><button key={c.id} className={"conversation-pill "+(conversation?.id===c.id?"chosen":"")} onClick={()=>selectConversation(c.id)}>{c.title}</button>)}</div>
    <div className="chat-body">{conversation?.messages?.length?conversation.messages.map((m:any,i:number)=><div className={"bubble "+m.role} key={i}><small>{m.role==="user"?"You":m.role==="assistant"?"Assistant":"System"}</small><p>{m.content}</p></div>):<Empty icon={MessageSquare} title="What would you like to work on?" detail="Conversation storage is available. AI responses are paused until the eligible ChatGPT-plan connection is configured."/>}</div>
    <form className="chat-input" onSubmit={sendChat}><input value={chatInput} onChange={e=>setChatInput(e.target.value)} placeholder="Ask your assistant…"/><button className="button primary" disabled={!conversation||!chatInput.trim()}><Send size={16}/></button></form>
   </div><aside className="task-panel"><div className="section-head"><h2>AI tasks</h2><span className="count-pill">{active.length} active · max 3</span></div>
    <form className="task-create" onSubmit={addTask}><input value={taskTitle} onChange={e=>setTaskTitle(e.target.value)} placeholder="Task title" required maxLength={500}/><textarea value={taskText} onChange={e=>setTaskText(e.target.value)} placeholder="Describe what you want done…"/>
     <label>Priority</label><select value={taskPriority} onChange={e=>setTaskPriority(e.target.value)}><option value="urgent">Urgent</option><option value="high">High</option><option value="normal">Normal</option><option value="low">Low</option></select>
     <label>Deadline (optional)</label><input type="datetime-local" value={deadline} onChange={e=>setDeadline(e.target.value)}/>{deadline&&<select value={deadlineType} onChange={e=>setDeadlineType(e.target.value)}><option value="target">Target deadline</option><option value="hard">Hard deadline</option></select>}
     <button className="button primary full"><Plus size={15}/> Add task</button></form>
    {tasks.map(t=><div className="task-card" key={t.id}><div className="row-top"><b>{t.title}</b><span className={"priority "+t.priority}>{t.priority}</span></div><small>{t.status.replaceAll("_"," ")} · {t.deadline_type||"No deadline"}</small><p>{t.blocker}</p><div className="inline-actions"><select aria-label="Task priority" value={t.priority_override_by_user?t.base_priority:"automatic"} onChange={async e=>{await api.priority(t.id,e.target.value==="automatic"?null:e.target.value);await refresh()}}><option value="automatic">Automatic</option><option value="urgent">Urgent</option><option value="high">High</option><option value="normal">Normal</option><option value="low">Low</option></select><button className="icon-button" title="Cancel task" onClick={async()=>{await api.cancelTask(t.id);await refresh()}}><X size={15}/></button></div></div>)}
   </aside></section>}
   {view==="Accounts & Settings"&&<section className="content-card"><div className="section-head"><div><h2>Email accounts</h2><p>Never use your normal Apple ID password here.</p></div><button className="button primary" onClick={()=>setShowAccount(true)}><Plus size={15}/> Add account</button></div>
    {accounts.length===0?<Empty title="No connected accounts" detail="Connect an iCloud mailbox to begin." action={<button className="button secondary" onClick={()=>setShowAccount(true)}>Connect account</button>}/>:accounts.map(a=><div className="account-row" key={a.id}><div className="account-icon"><Mail size={18}/></div><div><b>{a.email}</b><small>{a.provider.toUpperCase()} · {a.status} · {a.last_sync_at?new Date(a.last_sync_at).toLocaleString():"Never synced"}</small></div><span className="spacer"/><button className="button secondary compact" onClick={async()=>{await api.syncOne(a.id);setNotice("Sync job queued.")}}>Sync now</button><button className="button secondary compact" onClick={async()=>{if(confirm("Disconnect account? Imported history remains.")){await api.disconnectAccount(a.id);await refresh()}}}>Disconnect</button></div>)}
    <div className="settings-block"><h3>AI connection and privacy</h3><p><AlertCircle size={15}/> Official ChatGPT-plan connection is not configured. No paid API fallback is active.</p><p><ShieldCheck size={15}/> Background AI processing is disabled until explicit consent and eligibility checks are completed.</p><a href="https://chatgpt.com/#settings/Usage" target="_blank" rel="noreferrer">Manage ChatGPT usage <ExternalLink size={12}/></a></div>
    <div className="settings-block"><h3>Automatic email review</h3><p><Clock size={15}/> Proposed times: 08:00, 12:00 and 17:00 IST. The cloud scheduler is not active yet.</p><p>No proactive notifications are configured.</p></div>
    <div className="settings-block"><h3>Current integration status</h3><p>iCloud: limited Inbox IMAP starter. Gmail OAuth, provider write-back, sending, attachments, Apple Shortcuts and background AI tasks still require implementation.</p></div>
   </section>}
   <footer>Private single-user workspace · Asia/Kolkata · No proactive notifications</footer>
  </main>
  {showAccount&&<div className="modal-backdrop"><form className="modal" onSubmit={connect}><div className="section-head"><h2>Connect email account</h2><button type="button" className="icon-button" onClick={()=>setShowAccount(false)}><X size={17}/></button></div><label>Provider</label><select value={provider} onChange={e=>setProvider(e.target.value)}><option value="icloud">iCloud Mail</option><option value="gmail">Gmail (OAuth not implemented)</option></select><label>Email address</label><input type="email" value={newEmail} onChange={e=>setNewEmail(e.target.value)} required/><label>Apple app-specific password</label><input type="password" value={appPassword} onChange={e=>setAppPassword(e.target.value)} disabled={provider!=="icloud"} required={provider==="icloud"}/><small>Only an Apple app-specific password is accepted. Gmail needs official Google OAuth; do not enter a Google password.</small><button className="button primary full" disabled={provider!=="icloud"}>Save and queue iCloud verification</button></form></div>}
 </div>;
}
