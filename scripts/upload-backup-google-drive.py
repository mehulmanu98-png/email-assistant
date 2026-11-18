#!/usr/bin/env python3
"""Upload encrypted Email Assistant backups to a dedicated Google Drive folder."""
import json, os, sys, urllib.parse, urllib.request, urllib.error

def required(name):
    value=os.environ.get(name)
    if not value: raise SystemExit("Missing required environment variable: "+name)
    return value

client_id=required("GOOGLE_CLIENT_ID")
client_secret=required("GOOGLE_CLIENT_SECRET")
refresh_token=required("GOOGLE_REFRESH_TOKEN")
folder_id=required("GOOGLE_DRIVE_FOLDER_ID")
backup_dir=os.environ.get("BACKUP_DIR",os.path.expanduser("~/email-assistant-backups"))
files=[os.path.join(backup_dir,n) for n in os.listdir(backup_dir)
       if n.endswith(".dump.enc") or n.endswith(".dump.enc.sha256")]
files=[p for p in files if os.path.isfile(p)]
if not files: raise SystemExit("No encrypted backup or checksum files found.")
def request(url,data=None,headers=None,method=None):
    req=urllib.request.Request(url,data=data,headers=headers or {},method=method)
    try:
        with urllib.request.urlopen(req,timeout=90) as r: return r.read()
    except urllib.error.HTTPError as e:
        detail=e.read(2000).decode("utf-8","replace")
        raise SystemExit("Google Drive API error %s: %s"%(e.code,detail))
token_data=urllib.parse.urlencode({
    "client_id":client_id,"client_secret":client_secret,
    "refresh_token":refresh_token,"grant_type":"refresh_token"}).encode()
token=json.loads(request("https://oauth2.googleapis.com/token",token_data,
                         {"Content-Type":"application/x-www-form-urlencoded"}))
access=token["access_token"]
auth={"Authorization":"Bearer "+access}
def upload(path):
    name=os.path.basename(path)
    metadata=json.dumps({"name":name,"parents":[folder_id]}).encode()
    boundary="emailassistantbackupboundary"
    body=(b"--"+boundary.encode()+b"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"+
          metadata+b"\r\n--"+boundary.encode()+b"\r\nContent-Type: application/octet-stream\r\n\r\n"+
          open(path,"rb").read()+b"\r\n--"+boundary.encode()+b"--")
    result=json.loads(request("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,size",
        body,{**auth,"Content-Type":"multipart/related; boundary="+boundary}))
    print("Uploaded %s (%s bytes)"%(result["name"],result.get("size","unknown")))
for path in sorted(files): upload(path)
# Retain the newest 16 encrypted backups, deleting each checksum sidecar with its dump.
query=urllib.parse.urlencode({"q":"'"+folder_id+"' in parents and trashed=false and name contains '.dump.enc'",
    "pageSize":100,"orderBy":"createdTime desc","fields":"files(id,name,createdTime)"})
listing=json.loads(request("https://www.googleapis.com/drive/v3/files?"+query,None,auth))
backups=[x for x in listing.get("files",[]) if x["name"].endswith(".dump.enc")]
for old in backups[16:]:
    request("https://www.googleapis.com/drive/v3/files/"+old["id"],None,auth,"DELETE")
    sidecar_name=old["name"]+".sha256"
    side_query=urllib.parse.urlencode({"q":"'"+folder_id+"' in parents and trashed=false and name='"+sidecar_name+"'",
        "pageSize":10,"fields":"files(id,name)"})
    sidecars=json.loads(request("https://www.googleapis.com/drive/v3/files?"+side_query,None,auth))
    for sidecar in sidecars.get("files",[]):
        request("https://www.googleapis.com/drive/v3/files/"+sidecar["id"],None,auth,"DELETE")
    print("Pruned old backup and checksum: "+old["name"])
