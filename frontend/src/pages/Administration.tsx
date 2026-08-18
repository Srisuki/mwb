import {useState} from 'react';
import {RolePermissionsPanel} from '../features/users/components/RolePermissionsPanel';
import {UsersPage} from '../features/users/pages/UsersPage';
import {api} from '../services/api';

export function AdminPage(){
  const [backup,setBackup]=useState<File|null>(null),[message,setMessage]=useState('');
  async function migrate(){
    if(!backup)return;
    const data=new FormData();data.set('file',backup);
    try{const result=await api.migrateLegacy(data);setMessage(`Migration complete: ${JSON.stringify(result)}`)}
    catch(reason){setMessage(`Error: ${(reason as Error).message}`)}
  }
  return <>
    <UsersPage/>
    <RolePermissionsPanel/>
    <section className="panel legacy-import"><h2>Import legacy JSON backup</h2><p className="muted">The source backup remains untouched. Invalid and unmatched records are reported. Legacy PINs are never imported.</p><div className="form-grid"><label>Backup JSON<input type="file" accept=".json,application/json" onChange={event=>setBackup(event.target.files?.[0]||null)}/></label><button className="primary" disabled={!backup} onClick={migrate}>Validate and import</button></div>{message&&<div className={message.startsWith('Error:')?'alert':'notice'}>{message}</div>}</section>
  </>;
}
