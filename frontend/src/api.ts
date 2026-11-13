const API = "/api";
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(API + path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  const data = await response.json().catch(() => ({ detail: "Unexpected server response" }));
  if (!response.ok) throw new Error(data.detail || "Request failed");
  return data as T;
}
export const api = {
  me: () => request<{id:number; email:string}>("/auth/me"),
  login: (email:string,password:string) => request<{email:string}>("/auth/login",{method:"POST",body:JSON.stringify({email,password})}),
  logout: () => request("/auth/logout",{method:"POST"}),
  accounts: () => request<any[]>("/accounts"),
  addAccount: (email:string,app_password:string) => request<any>("/accounts",{method:"POST",body:JSON.stringify({provider:"icloud",email,app_password})}),
  disconnectAccount: (id:number) => request<any>("/accounts/"+id,{method:"DELETE"}),
  messages: (q:string) => request<any[]>("/messages?q="+encodeURIComponent(q)),
  message: (id:number) => request<any>("/messages/"+id),
  markRead: (id:number) => request<any>("/messages/"+id+"/read",{method:"POST"}),
  trash: (id:number) => request<any>("/messages/"+id,{method:"DELETE"}),
  block: (id:number) => request<any>("/messages/"+id+"/block",{method:"POST"}),
  createDraft: (id:number) => request<any>("/messages/"+id+"/draft",{method:"POST"}),
  saveDraft: (id:number,data:any) => request<any>("/drafts/"+id,{method:"PATCH",body:JSON.stringify(data)}),
  sendDraft: (id:number,updated_at:string) => request<any>("/drafts/"+id+"/send",{method:"POST",body:JSON.stringify({confirm_send:true,expected_updated_at:updated_at})}),
  sync: () => request<any>("/sync",{method:"POST"}),
  syncOne: (id:number) => request<any>("/sync/"+id,{method:"POST"}),
  followups: () => request<any[]>("/followups"),
  completeFollowup: (id:number) => request<any>("/followups/"+id+"/complete",{method:"PATCH"}),
  removeFollowup: (id:number) => request<any>("/followups/"+id,{method:"DELETE"}),
  tasks: () => request<any[]>("/tasks"),
  addTask: (data:any) => request<any>("/tasks",{method:"POST",body:JSON.stringify(data)}),
  priority: (id:number,priority:string|null) => request<any>("/tasks/"+id+"/priority",{method:"PATCH",body:JSON.stringify(priority?{priority}:{automatic:true})}),
  cancelTask: (id:number) => request<any>("/tasks/"+id+"/cancel",{method:"PATCH"}),
  conversations: () => request<any[]>("/conversations"),
  newConversation: (title:string) => request<any>("/conversations",{method:"POST",body:JSON.stringify({title})}),
  conversation: (id:number) => request<any>("/conversations/"+id),
  sendMessage: (id:number,content:string) => request<any>("/conversations/"+id+"/messages",{method:"POST",body:JSON.stringify({content})})
};
