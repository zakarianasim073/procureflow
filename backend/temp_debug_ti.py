import json
from pathlib import Path

rt_dir = Path(r'D:\A1\procurementflow_final_v3\procurementflow\backend\runtime\data_intel')
json_path = rt_dir / 'bwdb_all_tenders.json'
print(f'File exists: {json_path.exists()}')
print(f'File size: {json_path.stat().st_size}')

try:
    data = json.loads(json_path.read_text(encoding='utf-8'))
    all_t = data.get('bwdb_all', [])
    print(f'bwdb_all count: {len(all_t)}')
    if all_t:
        print(f'First tender_id: {all_t[0].get("tender_id", "")}')
except Exception as e:
    print(f'ERROR: {e}')
