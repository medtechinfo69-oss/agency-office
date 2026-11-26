import { useEffect, useState } from 'react'
import { api } from '../api'
import App from '../App'
import SaaSWorkspace from './SaaSWorkspace'
import AccountSecurity from './AccountSecurity'
import { Button, Empty, InlineNotice, Skeleton } from './admin-ui'
export default function SaaSEntry({onLogout}) {
 const [data,setData]=useState(null),[error,setError]=useState(''),[notice,setNotice]=useState('')
 const load=()=>{setError('');api.get('/saas/me').then(setData).catch(e=>setError(e.message))}
 useEffect(()=>{load()},[])
 if(error)return <main className="page a-admin"><Empty title="Workspace access unavailable" description={error} action={<><Button onClick={load}>Retry</Button><Button onClick={onLogout}>Sign out</Button></>}/></main>
 if(!data)return <main className="page a-admin"><Skeleton/></main>
 if(data.mfa_required)return <main className="page a-admin"><h1>Secure your Boss Admin account</h1><InlineNotice tone="warning">Two-factor authentication is mandatory before accessing platform management. Save your recovery codes securely.</InlineNotice>{notice&&<InlineNotice>{notice}</InlineNotice>}<AccountSecurity notify={setNotice}/><Button variant="primary" onClick={load}>I enabled 2FA — continue</Button><Button onClick={onLogout}>Sign out</Button></main>
 if(data.user.tenant_id)return <SaaSWorkspace initial={data} onLogout={onLogout}/>
 return <App onLogout={onLogout}/>
}
