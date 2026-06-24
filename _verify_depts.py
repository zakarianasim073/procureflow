import httpx, re
EGP_BASE = 'https://www.eprocure.gov.bd'
c = httpx.Client(verify=False, timeout=30, follow_redirects=True)
c.get(EGP_BASE)
c.post(f'{EGP_BASE}/LoginSrBean?action=checkLogin', data={'emailId':'hbsrjv@gmail.com','password':'hbsrjv2017'})
c.get(f'{EGP_BASE}/Index.jsp')

for name, dept_id in [('LGED',5), ('RHD',10), ('PWD',21), ('BADC',39), ('HED',141), ('Ctg Port Authority',102)]:
    r = c.post(f'{EGP_BASE}/ComboServlet', data={'departmentId':str(dept_id), 'funName':'peofficeCombo'})
    opts = re.findall(r'<option[^>]*value=(["\'])([^"\']+)\1[^>]*>(.*?)</option>', r.text, re.DOTALL)
    valid = [(v,t) for _,v,t in opts if v.strip() and v.strip()!=' ']
    print(f'{name} (dept={dept_id}): {len(valid)} offices')
    if valid:
        for v,t in valid[:5]:
            clean = re.sub(r'<[^>]+>', '', t).strip()
            print(f'  {v}: {clean[:70]}')
        if len(valid)>5:
            print(f'  ... and {len(valid)-5} more')
