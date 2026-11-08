from __future__ import annotations
import argparse,csv,hashlib,json,random
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def clean(v):
    t=str(v or '').strip()
    return '' if t.lower() in {'nan','none','null'} else t
def text(row):
    parts=[f'商品大类：{clean(row.get("product_type"))}',f'细分类：{clean(row.get("type"))}',f'颜色：{clean(row.get("color"))}',f'材质：{clean(row.get("material"))}']
    if clean(row.get('item_name')): parts.append(f'商品标题：{clean(row["item_name"])}')
    d=clean(row.get('description'))
    if d and not d.startswith('商品大类：'): parts.append(f'商品描述：{d}')
    return '；'.join(parts)
def read_rows(root):
    out=[]
    for p in sorted(root.glob('*/products.csv')):
        with p.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                if clean(r.get('item_id')): r['_category_dir']=p.parent.name; out.append(r)
    if not out: raise FileNotFoundError(f'未找到商品表：{root}')
    return out
def sample(rows,n,seed):
    rng=random.Random(seed); groups={}
    for r in rows: groups.setdefault(clean(r.get('product_type')) or r['_category_dir'],[]).append(r)
    for v in groups.values(): rng.shuffle(v)
    result=[]
    while len(result)<n:
        moved=False
        for k in sorted(groups):
            if groups[k] and len(result)<n: result.append(groups[k].pop()); moved=True
        if not moved: break
    return result
def make(r,i,kind):
    cat=clean(r.get('product_type')) or r['_category_dir']; sub=clean(r.get('type')); color=clean(r.get('color')); title=clean(r.get('item_name')); q=' '.join(x for x in (color,sub or cat) if x).strip() or title
    base={'id':f'{kind}_{i:03d}','task':kind,'item_id':clean(r['item_id']),'category':cat}
    if kind=='attribute': base.update(instruction='根据商品信息提取商品大类、细分类、颜色和材质，并生成标准商品描述。只输出模板描述。',input=text(r),output=f'商品大类：{cat}；细分类：{sub}；颜色：{color}；材质：{clean(r.get("material"))}')
    elif kind=='intent': base.update(instruction='解析用户商品检索需求，输出结构化意图 JSON，不要编造商品信息。',input=f'我想找{q}，推荐 5 件。',output=json.dumps({'intent':'search_products','query':q,'category':cat,'top_k':5},ensure_ascii=False,separators=(',',':')))
    else: base.update(instruction='把用户需求转换为白名单检索工具调用参数，只输出 JSON。',input=f'帮我搜索{q}，限制在{cat}类，返回 5 个结果。',output=json.dumps({'tool':'text_search','arguments':{'query':q,'category':cat,'top_k':5}},ensure_ascii=False,separators=(',',':')))
    return base
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input-dir',default='data/processed_data_cleaning'); ap.add_argument('--output',default='data/agent/agent_finetune_data.json'); ap.add_argument('--manifest',default='data/agent/agent_finetune_manifest.json'); ap.add_argument('--count',type=int,default=100); ap.add_argument('--seed',type=int,default=42); a=ap.parse_args()
    rows=read_rows((ROOT/a.input_dir).resolve()); picked=sample(rows,a.count,a.seed)
    if len(picked)!=a.count: raise RuntimeError(f'样本不足，需要 {a.count}，实际 {len(picked)}')
    data=[make(r,i,'attribute') for i,r in enumerate(picked[:60],1)]+[make(r,i,'intent') for i,r in enumerate(picked[60:85],61)]+[make(r,i,'tool_call') for i,r in enumerate(picked[85:],86)]
    out=(ROOT/a.output).resolve(); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    manifest={'schema_version':1,'created_at':datetime.now(timezone.utc).isoformat(),'source':a.input_dir,'output':a.output,'seed':a.seed,'record_count':len(data),'task_counts':dict(Counter(x['task'] for x in data)),'category_counts':dict(sorted(Counter(x['category'] for x in data).items())),'source_rows_available':len(rows),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
    mp=(ROOT/a.manifest).resolve(); mp.parent.mkdir(parents=True,exist_ok=True); mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(f'生成 {len(data)} 条：{out}'); print(f'清单：{mp}')
if __name__=='__main__': main()
