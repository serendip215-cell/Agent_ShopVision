import json,re
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
root=Path(__file__).parent
with open(root/'summary.json',encoding='utf-8') as f: s=json.load(f)
plt.rcParams.update({'figure.dpi':160,'savefig.dpi':220,'font.size':11,'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False})
labels=['Raw data','Cleaned data']
totals=[10165,9393]; train=[8146,7520]; valid=[1019,939]; test=[1000,934]
fig,ax=plt.subplots(figsize=(9,5.5)); x=np.arange(2); w=.2
for i,(name,vals,c) in enumerate(zip(['Train','Valid','Test'],[train,valid,test],['#4c78a8','#f58518','#54a24b'])):
    b=ax.bar(x+(i-1)*w,vals,w,label=name,color=c); ax.bar_label(b,fmt='%d',fontsize=8,padding=2)
ax.set_xticks(x,labels); ax.set_ylabel('Samples'); ax.set_title('Dataset size before and after cleaning'); ax.legend(); ax.grid(axis='y',alpha=.25); fig.tight_layout(); fig.savefig(root/'04_sample_count.png'); plt.close(fig)
fig,ax=plt.subplots(figsize=(8,5.5)); b=ax.bar(['Removed as noise','Retained'],[772,9393],color=['#e45756','#54a24b']); ax.bar_label(b,fmt='%d',padding=3); ax.set_ylabel('Samples'); ax.set_title('Cleaning outcome'); ax.grid(axis='y',alpha=.25); fig.tight_layout(); fig.savefig(root/'05_cleaning_outcome.png'); plt.close(fig)
names=['R@1','R@5','R@10','Mean Recall']; base=s['models']['预训练基线']; unc=s['models']['未清洗数据训练']; clean=s['models']['清洗数据训练']
fig,axs=plt.subplots(2,2,figsize=(12,8));
axs[0,0].bar(['Baseline','Uncleaned','Cleaned'],[base['r1'],unc['r1'],clean['r1']],color=['#8da0cb','#fc8d62','#66c2a5']); axs[0,0].set_title('R@1 (%)'); axs[0,0].set_ylim(0,70)
for ax,k,title in [(axs[0,1],'r5','R@5 (%)'),(axs[1,0],'r10','R@10 (%)'),(axs[1,1],'mean_recall','Mean Recall (%)')]: ax.bar(['Baseline','Uncleaned','Cleaned'],[base[k],unc[k],clean[k]],color=['#8da0cb','#fc8d62','#66c2a5']); ax.set_title(title); ax.set_ylim(0,105)
for ax in axs.flat: ax.grid(axis='y',alpha=.22)
fig.suptitle('Evaluation dashboard: model and data quality effects',fontsize=15); fig.tight_layout(); fig.savefig(root/'06_evaluation_dashboard.png'); plt.close(fig)
raw_epochs=[1,2,3]; raw_loss=[.411319,.333275,.327270]; raw_i2t=[84.47,87.21,88.87]; raw_t2i=[85.35,87.89,89.26]
fig,ax=plt.subplots(figsize=(9,5.5)); ax.plot(raw_epochs,raw_loss,marker='o',label='Valid loss',color='#e45756'); ax.set_xlabel('Epoch'); ax.set_ylabel('Validation loss'); ax.set_xticks(raw_epochs); ax.set_title('Uncleaned training validation trend from submitted log'); ax.grid(alpha=.25); ax.legend(); fig.tight_layout(); fig.savefig(root/'07_uncleaned_validation_loss.png'); plt.close(fig)
fig,ax=plt.subplots(figsize=(9,5.5)); ax.plot(raw_epochs,raw_i2t,marker='o',label='Image-to-Text',color='#4c78a8'); ax.plot(raw_epochs,raw_t2i,marker='o',label='Text-to-Image',color='#f58518'); ax.set_xlabel('Epoch'); ax.set_ylabel('Batch validation accuracy (%)'); ax.set_ylim(0,100); ax.set_xticks(raw_epochs); ax.set_title('Uncleaned training validation accuracy'); ax.grid(alpha=.25); ax.legend(); fig.tight_layout(); fig.savefig(root/'08_uncleaned_validation_accuracy.png'); plt.close(fig)
print('extended charts generated')
