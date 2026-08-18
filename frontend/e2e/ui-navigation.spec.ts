import {expect,test} from '@playwright/test';

test('authenticated user can navigate production workflow forms',async({page})=>{
  const email=process.env.E2E_EMAIL,password=process.env.E2E_PASSWORD;
  test.skip(!email||!password,'Set E2E_EMAIL and E2E_PASSWORD');
  await page.goto('/');
  await page.getByLabel('Email').fill(email!);
  await page.getByLabel('Password').fill(password!);
  await page.getByRole('button',{name:'Sign in'}).click();
  await expect(page.getByRole('heading',{name:'Overview'})).toBeVisible();
  for(const name of ['Audit calendar','Audit entry','Observations','Client replies','Reports & approval','Documents','Masters','User controls']){
    await page.getByRole('link',{name}).click();
    await expect(page.getByRole('heading',{name,level:1})).toBeVisible();
  }
  await expect(page.getByRole('heading',{name:'User controls',exact:true}).last()).toBeVisible();
});
