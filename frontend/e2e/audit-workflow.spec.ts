import {expect,test} from '@playwright/test';

test('complete audit workflow locks authoritative records',async({request})=>{
  const email=process.env.E2E_EMAIL,password=process.env.E2E_PASSWORD;
  test.skip(!email||!password,'Set E2E_EMAIL and E2E_PASSWORD');
  const login=await request.post('/api/auth/login',{data:{email,password}});expect(login.ok()).toBeTruthy();
  const tokens=await login.json(),headers={Authorization:`Bearer ${tokens.access_token}`},suffix=Date.now().toString();
  const temporaryPassword=`Workflow-${suffix}-Secure!`;
  const entityResponse=await request.post('/api/entities',{headers,data:{name:`E2E Entity ${suffix}`,code:`E${suffix.slice(-5)}`}});expect(entityResponse.status()).toBe(201);const entity=await entityResponse.json();
  const createUser=async(role_name:string,label:string,entity_ids:string[] = [])=>{const response=await request.post('/api/users',{headers,data:{email:`${label}-${suffix}@example.com`,full_name:`E2E ${label}`,role_name,temporary_password:temporaryPassword,entity_ids}});expect(response.status()).toBe(201);return response.json()};
  const staff=await createUser('Audit Staff','staff',[entity.id]),client=await createUser('Client Management','client',[entity.id]),manager=await createUser('Audit Manager','manager',[entity.id]);
  const loginAs=async(userEmail:string,label:string)=>{const first=await request.post('/api/auth/login',{data:{email:userEmail,password:temporaryPassword}});expect(first.ok()).toBeTruthy();const firstTokens=await first.json(),newPassword=`Changed-${label}-${suffix}-Secure!`;const changed=await request.post('/api/auth/change-password',{headers:{Authorization:`Bearer ${firstTokens.access_token}`},data:{current_password:temporaryPassword,new_password:newPassword}});expect(changed.status()).toBe(204);const response=await request.post('/api/auth/login',{data:{email:userEmail,password:newPassword}});expect(response.ok()).toBeTruthy();return {Authorization:`Bearer ${(await response.json()).access_token}`}};
  const staffHeaders=await loginAs(staff.email,'staff'),clientHeaders=await loginAs(client.email,'client'),managerHeaders=await loginAs(manager.email,'manager');
  const areas=await (await request.get('/api/audit-areas',{headers})).json();expect(areas.length).toBeGreaterThan(0);
  const checks=await (await request.get('/api/checklists',{headers})).json();expect(checks.length).toBe(131);
  const period='2099-01';
  const plan=await request.post('/api/audit-plans',{headers:managerHeaders,data:{entity_id:entity.id,audit_area_id:areas[0].id,period,due_date:'2099-01-31',assigned_user_ids:[staff.id]}});expect(plan.status()).toBe(201);
  const observations=[];
  for(const check of checks){const created=await request.post('/api/observations',{headers:staffHeaders,data:{entity_id:entity.id,audit_plan_id:null,audit_area_id:check.audit_area_id,checklist_item_id:check.id,period,risk:'Low',status:'Pending',observation:'No adverse observation',remark:'E2E verified',responsible_person:'Audit Team',due_date:null}});expect(created.status()).toBe(201);observations.push(await created.json())}
  const forbidden=await request.post('/api/entities',{headers:staffHeaders,data:{name:`Forbidden ${suffix}`}});expect(forbidden.status()).toBe(403);
  const visibleEntities=await (await request.get('/api/entities',{headers:clientHeaders})).json();expect(visibleEntities.map((item:{id:string})=>item.id)).toEqual([entity.id]);
  const uploaded=await request.post('/api/documents/upload',{headers:staffHeaders,multipart:{entity_id:entity.id,audit_area_id:checks[0].audit_area_id,observation_id:observations[0].id,checklist_item_id:checks[0].id,period,document_type:'Supporting Evidence',remarks:'E2E evidence',file:{name:'e2e-evidence.txt',mimeType:'text/plain',buffer:Buffer.from('authoritative audit evidence')}}});expect(uploaded.status(),await uploaded.text()).toBe(201);const document=await uploaded.json();expect(document.checksum).toHaveLength(64);
  const downloaded=await request.get(`/api/documents/${document.id}/download`,{headers:clientHeaders});expect(downloaded.ok()).toBeTruthy();expect((await downloaded.text())).toBe('authoritative audit evidence');
  const reply=await request.post(`/api/observations/${observations[0].id}/replies`,{headers:clientHeaders,data:{comment:'Management confirms control completion',action_taken:'Evidence provided'}});expect(reply.status()).toBe(201);
  const review=await request.patch(`/api/observations/${observations[0].id}`,{headers:managerHeaders,data:{status:'Resolved',remark:'Auditor reviewed management evidence',expected_version:2}});expect(review.ok()).toBeTruthy();
  const generated=await request.post('/api/reports/generate',{headers:managerHeaders,data:{entity_id:entity.id,period,report_type:'Monthly Internal Audit Report'}});expect(generated.status()).toBe(201);const report=await generated.json();
  const approved=await request.post(`/api/reports/${report.id}/approve`,{headers:managerHeaders});expect(approved.ok()).toBeTruthy();expect((await approved.json()).status).toBe('Locked');
  const lockedEdit=await request.patch(`/api/observations/${observations[1].id}`,{headers:staffHeaders,data:{remark:'Must fail',expected_version:1}});expect(lockedEdit.status()).toBe(409);
  for(const format of ['csv','xlsx','docx','pdf']){const exported=await request.get(`/api/reports/${report.id}/export/${format}`,{headers});expect(exported.ok()).toBeTruthy();expect((await exported.body()).length).toBeGreaterThan(100)}
  const archived=await request.delete(`/api/documents/${document.id}`,{headers:staffHeaders});expect(archived.status()).toBe(204);const afterArchive=await request.get(`/api/documents/${document.id}/download`,{headers:staffHeaders});expect(afterArchive.status()).toBe(404);
});
