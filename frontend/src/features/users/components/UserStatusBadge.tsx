export function UserStatusBadge({active}:{active:boolean}){return <span className={`badge ${active?'completed':'critical'}`}>{active?'Active':'Inactive'}</span>}
