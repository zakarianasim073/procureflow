import httpx, re
EGP_BASE = 'https://www.eprocure.gov.bd'
c = httpx.Client(verify=False, timeout=30, follow_redirects=True)
c.get(EGP_BASE)
c.post(f'{EGP_BASE}/LoginSrBean?action=checkLogin', data={'emailId':'hbsrjv@gmail.com','password':'hbsrjv2017'})
c.get(f'{EGP_BASE}/Index.jsp')

# Try both funName values for each department
tests = [('LGED',5), ('RHD',10), ('PWD',21), ('BWDB',7)]
for name, dept_id in tests:
    for fun in ['officeCombo', 'peofficeCombo']:
        # Try without districtId
        r = c.post(f'{EGP_BASE}/ComboServlet', data={'departmentId':str(dept_id), 'funName':fun})
        opts = re.findall(r'<option[^>]*value=(["\'])([^"\']+)\1[^>]*>(.*?)</option>', r.text, re.DOTALL)
        valid = [(v,t) for _,v,t in opts if v.strip() and v.strip()!=' ']
        
        # Also try with any districtId=0
        r2 = c.post(f'{EGP_BASE}/ComboServlet', data={'departmentId':str(dept_id), 'districtId':'0', 'funName':fun})
        opts2 = re.findall(r'<option[^>]*value=(["\'])([^"\']+)\1[^>]*>(.*?)</option>', r2.text, re.DOTALL)
        valid2 = [(v,t) for _,v,t in opts2 if v.strip() and v.strip()!=' ']
        
        print(f'{name} dept={dept_id} fun={fun}: {len(valid)} offices (no dist), {len(valid2)} offices (dist=0)')
        if valid:
            for v,t in valid[:2]:
                clean = re.sub(r'<[^>]+>', '', t).strip()
                print(f'  {v}: {clean[:60]}')
        if valid2 and not valid:
            for v,t in valid2[:2]:
                clean = re.sub(r'<[^>]+>', '', t).strip()
                print(f'  dist=0: {v}: {clean[:60]}')

# Also check what the raw response looks like for a failing case
print('\n--- Raw response for LGED (fun=officeCombo) ---')
r = c.post(f'{EGP_BASE}/ComboServlet', data={'departmentId':'5', 'funName':'officeCombo'})
print(r.text[:300])
print('--- Raw response for LGED (fun=peofficeCombo) ---')
r = c.post(f'{EGP_BASE}/ComboServlet', data={'departmentId':'5', 'funName':'peofficeCombo'})
print(r.text[:300])
