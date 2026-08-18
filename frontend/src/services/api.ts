const API_URL=import.meta.env.VITE_API_URL||"/api";
let accessToken=sessionStorage.getItem("mwb_access_token");let refreshToken=sessionStorage.getItem("mwb_refresh_token");
export const authStore={set(token:string,refresh?:string){accessToken=token;sessionStorage.setItem("mwb_access_token",token);if(refresh){refreshToken=refresh;sessionStorage.setItem("mwb_refresh_token",refresh)}},clear(){accessToken=null;refreshToken=null;sessionStorage.removeItem("mwb_access_token");sessionStorage.removeItem("mwb_refresh_token")},has(){return Boolean(accessToken)},refresh(){return refreshToken}};
export class ApiError extends Error{constructor(public status:number,message:string){super(message)}}
function errorMessage(detail:unknown):string{
  if(typeof detail==="string")return detail;
  if(Array.isArray(detail))return detail.map(item=>typeof item?.msg==="string"?item.msg:"Invalid request").join("; ");
  if(detail&&typeof detail==="object"&&"message" in detail&&typeof detail.message==="string")return detail.message;
  return "Request failed";
}
export async function request<T>(path:string,init:RequestInit={}):Promise<T>{
  const isForm=init.body instanceof FormData;
  const response=await fetch(`${API_URL}${path}`,{...init,headers:{...(!isForm?{"Content-Type":"application/json"}:{}),...(accessToken?{Authorization:`Bearer ${accessToken}`}:{ }),...init.headers}});
  if(response.status===401&&refreshToken&&path!=="/auth/refresh"){const refreshed=await fetch(`${API_URL}/auth/refresh`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({refresh_token:refreshToken})});if(refreshed.ok){const tokens=await refreshed.json();authStore.set(tokens.access_token,tokens.refresh_token);return request<T>(path,init)}authStore.clear()}
  if(response.status===204)return undefined as T;
  const data=await response.json().catch(()=>({detail:"The service returned an unexpected response"}));
  if(!response.ok)throw new ApiError(response.status,errorMessage(data.detail));
  return data as T;
}
export const api={
  login:(email:string,password:string)=>request<{access_token:string;refresh_token:string}>("/auth/login",{method:"POST",body:JSON.stringify({email,password})}),
  logout:()=>refreshToken?request<void>("/auth/logout",{method:"POST",body:JSON.stringify({refresh_token:refreshToken})}):Promise.resolve(),
  me:()=>request<import("../types").User>("/auth/me"),
  changePassword:(current_password:string,new_password:string)=>request<void>("/auth/change-password",{method:"POST",body:JSON.stringify({current_password,new_password})}),
  summary:()=>request<import("../types").Summary>("/dashboard/summary"),
  analytics:()=>request<{risk_distribution:{label:string;count:number}[];status_distribution:{label:string;count:number}[];entity_status:{label:string;count:number}[];period_status:{label:string;count:number}[];upcoming_audits:{entity:string;period:string;due_date:string}[]}>("/dashboard/analytics"),
  entities:()=>request<import("../types").Entity[]>("/entities"),
  createEntity:(data:{name:string;code?:string})=>request<import("../types").Entity>("/entities",{method:"POST",body:JSON.stringify(data)}),
  updateEntity:(id:string,data:Record<string,unknown>)=>request<import("../types").Entity>(`/entities/${id}`,{method:"PATCH",body:JSON.stringify(data)}),
  areas:()=>request<import("../types").Area[]>("/audit-areas"),
  createArea:(data:{name:string;description?:string;sort_order?:number})=>request<import("../types").Area>("/audit-areas",{method:"POST",body:JSON.stringify(data)}),
  updateArea:(id:string,data:Record<string,unknown>)=>request<import("../types").Area>(`/audit-areas/${id}`,{method:"PATCH",body:JSON.stringify(data)}),
  checklists:(areaId="")=>request<import("../types").Checklist[]>(`/checklists${areaId?`?audit_area_id=${areaId}`:""}`),
  createChecklist:(data:Record<string,unknown>)=>request<import("../types").Checklist>("/checklists",{method:"POST",body:JSON.stringify(data)}),
  updateChecklist:(id:string,data:Record<string,unknown>)=>request<import("../types").Checklist>(`/checklists/${id}`,{method:"PATCH",body:JSON.stringify(data)}),
  settings:()=>request<Record<string,{value?:string}|string>>("/settings"),
  updateSetting:(key:string,value:Record<string,unknown>)=>request(`/settings/${key}`,{method:"PUT",body:JSON.stringify({value})}),
  plans:(period="")=>request<import("../types").Plan[]>(`/audit-plans${period?`?period=${period}`:""}`),
  createPlan:(data:Record<string,unknown>)=>request<import("../types").Plan>("/audit-plans",{method:"POST",body:JSON.stringify(data)}),
  createFullMonthPlan:(data:Record<string,unknown>)=>request<import("../types").Plan[]>("/audit-plans/full-month",{method:"POST",body:JSON.stringify(data)}),
  updatePlan:(id:string,data:Record<string,unknown>)=>request<import("../types").Plan>(`/audit-plans/${id}`,{method:"PATCH",body:JSON.stringify(data)}),
  carryForward:(data:{entity_id:string;target_period:string})=>request<{count:number;source_period:string;target_period:string}>("/audit-plans/carry-forward",{method:"POST",body:JSON.stringify(data)}),
  observations:(filters:{entity_id?:string;audit_area_id?:string;period?:string;observation_status?:string}={})=>{const query=new URLSearchParams(Object.entries(filters).filter(([,value])=>Boolean(value)) as [string,string][]);return request<import("../types").Observation[]>(`/observations${query.size?`?${query}`:""}`)},
  updateObservation:(id:string,data:Record<string,unknown>)=>request<import("../types").Observation>(`/observations/${id}`,{method:"PATCH",body:JSON.stringify(data)}),
  observationHistory:(id:string)=>request<{id:string;action:string;old_value:Record<string,unknown>|null;new_value:Record<string,unknown>|null;created_at:string}[]>(`/observations/${id}/history`),
  exportObservations:async()=>{const response=await fetch(`${API_URL}/observations-export.csv`,{headers:accessToken?{Authorization:`Bearer ${accessToken}`}:{}});if(!response.ok)throw new ApiError(response.status,"Export failed");const url=URL.createObjectURL(await response.blob());const link=document.createElement("a");link.href=url;link.download="audit_observation_register.csv";link.click();URL.revokeObjectURL(url)},
  createObservation:(data:Record<string,unknown>)=>request<import("../types").Observation>("/observations",{method:"POST",body:JSON.stringify(data)}),
  reply:(id:string,data:{comment:string;action_taken:string})=>request(`/observations/${id}/replies`,{method:"POST",body:JSON.stringify(data)}),
  reports:()=>request<import("../types").Report[]>("/reports"),
  generateReport:(data:{entity_id:string;period:string;report_type:string})=>request<import("../types").Report>("/reports/generate",{method:"POST",body:JSON.stringify(data)}),
  approveReport:(id:string)=>request<import("../types").Report>(`/reports/${id}/approve`,{method:"POST"}),
  downloadReport:async(id:string,format:string)=>{const response=await fetch(`${API_URL}/reports/${id}/export/${format}`,{headers:accessToken?{Authorization:`Bearer ${accessToken}`}:{}});if(!response.ok){const data=await response.json().catch(()=>({detail:"Export failed"}));throw new ApiError(response.status,data.detail||"Export failed")}const url=URL.createObjectURL(await response.blob());const link=document.createElement("a");link.href=url;link.download=`audit-report.${format}`;link.click();URL.revokeObjectURL(url)},
  documents:()=>request<import("../types").DocumentRecord[]>("/documents"),
  uploadDocument:(data:FormData)=>request<import("../types").DocumentRecord>("/documents/upload",{method:"POST",body:data}),
  archiveDocument:(id:string)=>request<void>(`/documents/${id}`,{method:"DELETE"}),
  downloadDocument:async(id:string,fileName:string)=>{const response=await fetch(`${API_URL}/documents/${id}/download`,{headers:accessToken?{Authorization:`Bearer ${accessToken}`}:{}});if(!response.ok)throw new ApiError(response.status,"Download failed");const url=URL.createObjectURL(await response.blob());const link=document.createElement("a");link.href=url;link.download=fileName;link.click();URL.revokeObjectURL(url)},
  users:(filters:Record<string,string|number|undefined>={})=>{const query=new URLSearchParams(Object.entries(filters).filter(([,value])=>value!==undefined&&value!=='').map(([key,value])=>[key,String(value)]));return request<import("../types").User[]>(`/users${query.size?`?${query}`:""}`)},
  user:(id:string)=>request<import("../types").UserDetail>(`/users/${id}`),
  roles:()=>request<import("../types").Role[]>("/roles"),
  permissions:()=>request<{id:string;code:string;description:string}[]>("/permissions"),
  assignees:()=>request<import("../types").User[]>("/users/assignees"),
  createUser:(data:Record<string,unknown>)=>request<import("../types").User>("/users",{method:"POST",body:JSON.stringify(data)}),
  updateUser:(id:string,data:Record<string,unknown>)=>request<import("../types").User>(`/users/${id}`,{method:"PATCH",body:JSON.stringify(data)}),
  activateUser:(id:string)=>request<import("../types").User>(`/users/${id}/activate`,{method:"POST"}),
  deactivateUser:(id:string)=>request<import("../types").User>(`/users/${id}/deactivate`,{method:"POST"}),
  userPermissions:(id:string)=>request<string[]>(`/users/${id}/permissions`),
  userClients:(id:string)=>request<import("../types").Entity[]>(`/users/${id}/clients`),
  updateUserClients:(id:string,entity_ids:string[])=>request<import("../types").Entity[]>(`/users/${id}/clients`,{method:"PUT",body:JSON.stringify({entity_ids})}),
  migrateLegacy:(data:FormData)=>request<Record<string,unknown>>("/migrations/legacy-json",{method:"POST",body:data}),
};
