import type {Role} from '../../../types';
export function RoleSelector({roles,value,onChange}:{roles:Role[];value:string;onChange:(value:string)=>void}){return <label>Role *<select required value={value} onChange={event=>onChange(event.target.value)}><option value="">Select role</option>{roles.map(role=><option key={role.id} value={role.name}>{role.name}</option>)}</select></label>}
