export function getAuth(app){ return {app}; }
export function onAuthStateChanged(auth, cb){ setTimeout(()=>cb(null),0); return ()=>{}; }
export async function signInAnonymously(auth){ return {user:{uid:"anon"}}; }
