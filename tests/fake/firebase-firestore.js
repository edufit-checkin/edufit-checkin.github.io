const API = "http://127.0.0.1:8765";
export function initializeFirestore(){ return {}; }
export function getFirestore(){ return {}; }
export function persistentLocalCache(){ return {}; }
export function persistentMultipleTabManager(){ return {}; }
export function serverTimestamp(){ return "__ts__"; }
export function arrayUnion(...v){ return {"__au": v}; }
export function doc(db,...segs){ return {type:"doc", path:segs.join("/"), id:segs[segs.length-1]}; }
export function collection(db,...segs){ return {type:"col", path:segs.join("/")}; }
export async function setDoc(ref,data){
  const r = await fetch(API+"/set",{method:"POST",body:JSON.stringify({path:ref.path,data})});
  if (!r.ok) throw new Error("set failed");
}
export async function deleteDoc(ref){ await fetch(API+"/del",{method:"POST",body:JSON.stringify({path:ref.path})}); }
async function fetchDoc(path){ const r=await fetch(API+"/get?path="+encodeURIComponent(path)); return await r.json(); }
function wrapDoc(id,data){ return {id, exists:()=>data!==null, data:()=>data}; }
export async function getDoc(ref){ const d=await fetchDoc(ref.path); return wrapDoc(ref.id,d); }
export function writeBatch(){
  const ops=[]; return { set(ref,d){ops.push(["s",ref,d]);}, delete(ref){ops.push(["d",ref]);},
    async commit(){ for(const [t,r,d] of ops) t==="s"? await setDoc(r,d) : await deleteDoc(r); } };
}
export function onSnapshot(ref, a, b, c){
  let opts=a, cb=b, err=c;
  if (typeof a === "function"){ cb=a; err=b; }
  let stop=false, last=null;
  async function tick(){
    if(stop) return;
    try{
      if (ref.type==="doc"){
        const d=await fetchDoc(ref.path); const j=JSON.stringify(d);
        if (j!==last){ last=j; cb(wrapDoc(ref.id,d)); }
      } else {
        const r=await fetch(API+"/list?prefix="+encodeURIComponent(ref.path+"/"));
        const docs=await r.json();
        cb({forEach(f){docs.forEach(d=>f({id:d.id,data:()=>d.data}));}, metadata:{fromCache:false,hasPendingWrites:false}});
      }
    }catch(e){ err&&err(e); }
    setTimeout(tick,200);
  }
  tick(); return ()=>{stop=true;};
}
