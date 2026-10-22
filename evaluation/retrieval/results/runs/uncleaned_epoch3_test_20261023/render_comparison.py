import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
root=Path(__file__).parent
def load(n):
    with open(root/n,encoding='utf-8') as f: return json.load(f).get('scoreJson',{})
scores={'预训练基线':load('baseline_test_score.json'),'未清洗数据训练':load('uncleaned_epoch3_test_score.json'),'清洗数据训练':load('cleaned_epoch3_test_score.json')}
metrics=[('r1','R@1'),('r5','R@5'),('r10','R@10'),('mean_recall','Mean Recall')]
colors=['#8da0cb','#fc8d62','#66c2a5']
plt.rcParams.update({'figure.dpi':160,'savefig.dpi':220,'font.size':11,'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False})
x=np.arange(len(metrics)); width=.24
fig,ax=plt.subplots(figsize=(10,5.8))
for i,(name,d) in enumerate(scores.items()):
    vals=[d[k] for k,_ in metrics]; bars=ax.bar(x+(i-1)*width,vals,width,label=name,color=colors[i]); ax.bar_label(bars,fmt='%.2f',padding=2,fontsize=8)
ax.set_xticks(x,[n for _,n in metrics]); ax.set_ylim(0,110); ax.set_ylabel('Recall (%)'); ax.set_title('Text-to-Image retrieval comparison'); ax.grid(axis='y',alpha=.25); ax.legend(); fig.tight_layout(); fig.savefig(root/'01_recall_comparison.png'); plt.close(fig)
base=scores['预训练基线']; unc=scores['未清洗数据训练']; clean=scores['清洗数据训练']
fig,ax=plt.subplots(figsize=(10,5.8)); gu=[unc[k]-base[k] for k,_ in metrics]; gc=[clean[k]-unc[k] for k,_ in metrics]; b1=ax.bar(x-width/2,gu,width,label='Fine-tuning gain',color='#fc8d62'); b2=ax.bar(x+width/2,gc,width,label='Cleaning gain',color='#66c2a5'); ax.bar_label(b1,fmt='+%.2f',padding=2,fontsize=8); ax.bar_label(b2,fmt='+%.2f',padding=2,fontsize=8); ax.set_xticks(x,[n for _,n in metrics]); ax.set_ylabel('Gain (percentage points)'); ax.set_title('Contribution of fine-tuning and data cleaning'); ax.grid(axis='y',alpha=.25); ax.legend(); fig.tight_layout(); fig.savefig(root/'02_gain_contribution.png'); plt.close(fig)
fig,ax=plt.subplots(figsize=(8,5.5))
for name,d,c in zip(scores.keys(),scores.values(),colors): ax.plot([1,5,10],[d['r1'],d['r5'],d['r10']],marker='o',linewidth=2,label=name,color=c)
ax.set_xticks([1,5,10]); ax.set_xlabel('K'); ax.set_ylabel('Recall (%)'); ax.set_ylim(0,105); ax.set_title('Recall at K'); ax.grid(alpha=.25); ax.legend(); fig.tight_layout(); fig.savefig(root/'03_recall_curve.png'); plt.close(fig)
summary={'run_id':'uncleaned_epoch3_test_20261023','status':'reproduced_from_committed_evaluation_artifacts','evaluation_date':'2026-10-23','test_count':934,'candidate_pool':934,'models':scores,'provenance':{'uncleaned_run':'docs/finetune/runs/2026-10-20_uncleaned_bs32_lr1e-5/','cleaned_run':'evaluation/retrieval/results/runs/finetuned_epoch3_test_20261019/','note':'本轮未重新执行模型推理；Docker 引擎未运行且仓库不含大体积测试文件和训练权重，图表由已提交的评测凭证重新计算生成。'}}
with open(root/'summary.json','w',encoding='utf-8') as f: json.dump(summary,f,ensure_ascii=False,indent=2)
print('generated',root)
