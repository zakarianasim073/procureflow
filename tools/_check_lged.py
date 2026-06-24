import json

with open('backend/runtime/knowledge/app/offices_lged.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
offices = data if isinstance(data, list) else data.get('offices', data.get('data', []))
print(f'LGED offices: {len(offices)}')
for o in offices[:5]:
    print(f'  id={o["id"]} name={o["name"][:60]}')
print('...')
for o in offices[-3:]:
    print(f'  id={o["id"]} name={o["name"][:60]}')

skip_kw = ['circle', 'zone', 'director', 'secretariat', 'cell', 'board',
           'accounting', 'evaluation', 'programme', 'chief engineer',
           'project director', 'management unit', 'regional', 'hope',
           'audit', 'training', 'monitoring']
skipped = sum(1 for o in offices if any(kw in o['name'].lower() for kw in skip_kw))
print(f'\nWould skip (non-field office): {skipped}')
print(f'Would crawl: {len(offices) - skipped}')
