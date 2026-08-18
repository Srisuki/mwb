import {FormEvent,useEffect,useState} from "react";
import {api} from "../services/api";
import type {Area,Checklist,Entity,Observation,Plan} from "../types";

const month=()=>new Date().toISOString().slice(0,7);
const day=()=>new Date().toISOString().slice(0,10);
const statuses=['Pending','Management Responded','Resolved','Repeated','Closed'];
type Draft={observation:string;risk:string;status:string;remark:string;responsible_person:string;due_date:string};
const emptyDraft=():Draft=>({observation:'',risk:'Low',status:'Pending',remark:'',responsible_person:'',due_date:''});

function Notice({value}:{value:string}){return value?<div className={value.startsWith('Error:')?'alert':'notice'}>{value}</div>:null}
function useSetup(){const [entities,setEntities]=useState<Entity[]>([]),[areas,setAreas]=useState<Area[]>([]);useEffect(()=>{Promise.all([api.entities(),api.areas()]).then(([e,a])=>{setEntities(e);setAreas(a)})},[]);return {entities,areas}}

export function PlanningPage(){
  const {entities,areas}=useSetup(),[rows,setRows]=useState<Plan[]>([]),[msg,setMsg]=useState('');
  const [entity,setEntity]=useState(''),[area,setArea]=useState(''),[period,setPeriod]=useState(month()),[due,setDue]=useState(day());
  const reload=()=>api.plans().then(setRows);
  useEffect(()=>{reload()},[]);
  useEffect(()=>{if(!entity&&entities[0])setEntity(entities[0].id);if(!area&&areas[0])setArea(areas[0].id)},[entities,areas]);
  async function submit(e:FormEvent){e.preventDefault();try{await api.createPlan({entity_id:entity,audit_area_id:area,period,due_date:due,assigned_user_ids:[]});setMsg('Audit plan created');reload()}catch(x){setMsg(`Error: ${(x as Error).message}`)}}
  async function fullMonth(){try{const result=await api.createFullMonthPlan({entity_id:entity,period,due_date:due,assigned_user_ids:[]});setMsg(`${result.length} audit areas planned`);reload()}catch(x){setMsg(`Error: ${(x as Error).message}`)}}
  async function carry(){try{const result=await api.carryForward({entity_id:entity,target_period:period});setMsg(`${result.count} pending observations carried forward from ${result.source_period}`)}catch(x){setMsg(`Error: ${(x as Error).message}`)}}
  async function changeStatus(row:Plan,status:string){try{await api.updatePlan(row.id,{status,expected_version:row.version});setMsg('Plan status updated');reload()}catch(x){setMsg(`Error: ${(x as Error).message}`);reload()}}
  return <><section className="panel"><h2>Create monthly audit plan</h2><form className="form-grid" onSubmit={submit}><label>Entity<select required value={entity} onChange={e=>setEntity(e.target.value)}>{entities.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label><label>Audit area<select required value={area} onChange={e=>setArea(e.target.value)}>{areas.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label><label>Period<input required type="month" value={period} onChange={e=>setPeriod(e.target.value)}/></label><label>Due date<input required type="date" value={due} onChange={e=>setDue(e.target.value)}/></label><button className="primary">Create plan</button><button type="button" onClick={fullMonth}>Plan all areas</button><button type="button" onClick={carry}>Carry forward pending</button></form><Notice value={msg}/></section><section className="panel"><h2>Audit calendar</h2>{rows.map(row=><article className="report-row" key={row.id}><div><strong>{row.period}</strong><small>Due {row.due_date}</small></div><span className="badge">{row.status}</span><select value={row.status} onChange={e=>changeStatus(row,e.target.value)}>{['Pending','In Progress','Completed','Overdue'].map(x=><option key={x}>{x}</option>)}</select></article>)}</section></>;
}

export function AuditEntryPage(){
  const {entities,areas}=useSetup(),[entity,setEntity]=useState(''),[area,setArea]=useState(''),[period,setPeriod]=useState(month()),[items,setItems]=useState<Checklist[]>([]),[plans,setPlans]=useState<Plan[]>([]),[existing,setExisting]=useState<Record<string,Observation>>({}),[drafts,setDrafts]=useState<Record<string,Draft>>({}),[msg,setMsg]=useState(''),[loading,setLoading]=useState(false);
  useEffect(()=>{if(!entity&&entities[0])setEntity(entities[0].id);if(!area&&areas[0])setArea(areas[0].id)},[entities,areas]);
  useEffect(()=>{if(area)api.checklists(area).then(setItems)},[area]);
  useEffect(()=>{api.plans(period).then(setPlans)},[period]);
  useEffect(()=>{
    if(!entity||!area||!period)return;
    setLoading(true);
    api.observations({entity_id:entity,audit_area_id:area,period}).then(rows=>{
      const found=Object.fromEntries(rows.map(row=>[row.checklist_item_id,row]));
      setExisting(found);
      setDrafts(Object.fromEntries(items.map(item=>{
        const row=found[item.id];
        return [item.id,row?{observation:row.observation,risk:row.risk,status:row.status,remark:row.remark,responsible_person:row.responsible_person,due_date:row.due_date||''}:emptyDraft()];
      })));
    }).catch(x=>setMsg(`Error: ${x.message}`)).finally(()=>setLoading(false));
  },[entity,area,period,items]);
  function change(id:string,key:keyof Draft,value:string){setDrafts(current=>({...current,[id]:{...(current[id]||emptyDraft()),[key]:value}}))}
  async function submit(e:FormEvent){e.preventDefault();const mandatory=items.filter(x=>x.is_mandatory),missing=mandatory.filter(x=>!drafts[x.id]?.observation.trim());if(missing.length){setMsg(`Error: Complete all ${missing.length} remaining mandatory items`);return}setLoading(true);try{const plan=plans.find(item=>item.entity_id===entity&&item.audit_area_id===area);for(const item of items){const draft=drafts[item.id]||emptyDraft(),row=existing[item.id],data={risk:draft.risk,status:draft.status,observation:draft.observation,remark:draft.remark,responsible_person:draft.responsible_person,due_date:draft.due_date||null};if(row)await api.updateObservation(row.id,{...data,expected_version:row.version});else if(draft.observation.trim())await api.createObservation({entity_id:entity,audit_area_id:area,checklist_item_id:item.id,period,audit_plan_id:plan?.id||null,...data})}setMsg(`${items.length} checklist responses saved safely${plan?' and the audit plan status synchronized':''}`);const rows=await api.observations({entity_id:entity,audit_area_id:area,period});setExisting(Object.fromEntries(rows.map(row=>[row.checklist_item_id,row])))}catch(x){setMsg(`Error: ${(x as Error).message}. Reloaded the latest saved data.`)}finally{setLoading(false)}}
  return <section className="panel"><h2>Mandatory checklist entry</h2><form onSubmit={submit}><div className="form-grid"><label>Entity<select required value={entity} onChange={e=>setEntity(e.target.value)}>{entities.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label><label>Period<input required type="month" value={period} onChange={e=>setPeriod(e.target.value)}/></label><label>Audit area<select required value={area} onChange={e=>setArea(e.target.value)}>{areas.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label></div>{loading&&<div className="loading">Loading authoritative checklist data…</div>}<div className="checklist">{items.map((item,i)=>{const value=drafts[item.id]||emptyDraft();return <fieldset key={item.id}><legend>{i+1}. {item.question}{item.is_mandatory?' *':''}</legend><label>Observation<textarea required={item.is_mandatory} placeholder="Enter observation or ‘No adverse observation’" value={value.observation} onChange={e=>change(item.id,'observation',e.target.value)}/></label><div className="form-grid"><label>Risk<select value={value.risk} onChange={e=>change(item.id,'risk',e.target.value)}>{['Low','Medium','High','Critical'].map(x=><option key={x}>{x}</option>)}</select></label><label>Status<select value={value.status} onChange={e=>change(item.id,'status',e.target.value)}>{statuses.map(x=><option key={x}>{x}</option>)}</select></label><label>Responsible person<input value={value.responsible_person} onChange={e=>change(item.id,'responsible_person',e.target.value)}/></label><label>Due date<input type="date" value={value.due_date} onChange={e=>change(item.id,'due_date',e.target.value)}/></label></div><label>Auditor remark<textarea value={value.remark} onChange={e=>change(item.id,'remark',e.target.value)}/></label></fieldset>})}</div><button className="primary" disabled={!items.length||loading}>{loading?'Saving…':'Save complete audit area'}</button></form><Notice value={msg}/></section>;
}

export function ObservationRegisterPage(){
  const [rows,setRows]=useState<Observation[]>([]),[status,setStatus]=useState(''),[query,setQuery]=useState(''),[msg,setMsg]=useState('');const reload=()=>api.observations().then(setRows);useEffect(()=>{reload()},[]);const filtered=rows.filter(x=>(!status||x.status===status)&&(!query||x.observation.toLowerCase().includes(query.toLowerCase())));
  async function transition(row:Observation,next:string){try{await api.updateObservation(row.id,{status:next,expected_version:row.version});setMsg(`Observation moved to ${next}`);reload()}catch(x){setMsg(`Error: ${(x as Error).message}`);reload()}}
  return <section className="panel"><div className="panel-head"><h2>Observation register</h2><button onClick={()=>api.exportObservations()}>Export CSV</button></div><div className="form-grid"><label>Search<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search observations"/></label><label>Status<select value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>{statuses.map(x=><option key={x}>{x}</option>)}</select></label></div><Notice value={msg}/>{filtered.map(row=><article className="reply-card" key={row.id}><div><span className={`badge ${row.risk.toLowerCase()}`}>{row.risk}</span><strong>{row.observation}</strong><small>{row.period} · {row.responsible_person||'Unassigned'} · {row.locked_at?'Locked':row.status}</small></div><div>{row.remark||'No auditor remark'}</div>{!row.locked_at&&<select value={row.status} onChange={e=>transition(row,e.target.value)}>{statuses.map(x=><option key={x}>{x}</option>)}</select>}</article>)}</section>;
}
