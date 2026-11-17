"""Model acceptance rules: sealed samples never train, candidates must not be worse, switches are atomic."""
import hashlib,json
from datetime import datetime,timezone
from fastapi import HTTPException
from sqlalchemy import select,func
from .models import TrialHistory
from .governance_models import SealedBatch,ModelVersion,GovernanceState,GovernanceEvent
from .services import item,serialize
from .ml import fit_artifact,sealed_mae,MIN_TRAIN_ROWS
MIN_SEALED=8
def now(): return datetime.now(timezone.utc).isoformat()
def digest(ids): return hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest()
def event(s,u,action,version_no='',detail=''):
    s.add(GovernanceEvent(actor=u if isinstance(u,str) else u.email,action=action,version_no=version_no,detail=detail,stamp=now()))
def governance(s):
    g=s.get(GovernanceState,1)
    if not g:
        g=GovernanceState(id=1,epoch=0,active_version_id=None);s.add(g);s.flush()
    return g
def locked_governance(s):
    g=s.scalar(select(GovernanceState).where(GovernanceState.id==1).with_for_update())
    if not g: raise HTTPException(409,'治理状态未初始化')
    return g
def sealed_union(s):
    ids=set()
    for b in s.scalars(select(SealedBatch)): ids.update(b.sample_ids)
    return ids
def trainable_ids(s):
    blocked=sealed_union(s)
    return [r.id for r in s.scalars(select(TrialHistory).order_by(TrialHistory.id)) if r.id not in blocked]
def rows_by_ids(s,ids):
    return list(s.scalars(select(TrialHistory).where(TrialHistory.id.in_(ids)).order_by(TrialHistory.id))) if ids else []
def seal_batch(s,p,u):
    ids=sorted(set(p.trial_ids))
    if len(ids)<MIN_SEALED: raise HTTPException(409,f'封样批至少需要 {MIN_SEALED} 条试模样本')
    known={r.id for r in s.scalars(select(TrialHistory))}
    unknown=[i for i in ids if i not in known]
    if unknown: raise HTTPException(409,f'试模样本不存在：{unknown[:5]}')
    dup=sealed_union(s)&set(ids)
    if dup: raise HTTPException(409,f'{len(dup)} 条样本已在历史封样批中，封存不可重复')
    remaining=len(known)-len(sealed_union(s))-len(ids)
    if remaining<MIN_TRAIN_ROWS: raise HTTPException(409,f'封存后可用训练样本将不足 {MIN_TRAIN_ROWS} 条，不能封存')
    b=SealedBatch(name=p.name,sample_ids=ids,sample_count=len(ids),sample_hash=digest(ids),created_by=u.email,stamp=now())
    s.add(b);event(s,u,'封存验收样本',detail=f'{p.name} · {len(ids)} 条，历次训练永久排除');s.flush();return b
def create_candidate(s,u):
    if not s.scalar(select(SealedBatch.id)): raise HTTPException(409,'请先由负责人封存验收样本，再训练候选模型')
    ids=trainable_ids(s)
    if len(ids)<MIN_TRAIN_ROWS: raise HTTPException(409,f'排除封样后可用训练样本不足 {MIN_TRAIN_ROWS} 条')
    no=f"V{s.scalar(select(func.count()).select_from(ModelVersion))+1}"
    v=ModelVersion(version_no=no,status='training',train_sample_ids=ids,train_hash=digest(ids),created_by=u.email,stamp=now())
    s.add(v);event(s,u,'提交候选训练',no,f'固定 {len(ids)} 条非封样样本');s.flush();return v
def retry_candidate(s,vid,u):
    v=item(s,ModelVersion,vid)
    if v.status not in ('failed','training'): raise HTTPException(409,'仅训练中或训练失败的候选可重试')
    # Retry keeps the same candidate row and its frozen sample snapshot; it never spawns a duplicate.
    v.status='training';v.error='';event(s,u,'重试候选训练',v.version_no,'沿用原固定训练样本');return v
def train_version(s,vid):
    """Worker entry: train the frozen snapshot, then measure base-hours error on the sealed batch."""
    v=s.get(ModelVersion,vid)
    if not v or v.status!='training': return
    try:
        rows=rows_by_ids(s,v.train_sample_ids)
        if digest(v.train_sample_ids)!=v.train_hash: raise ValueError('候选训练样本快照校验失败')
        artifact,evidence=fit_artifact(rows)
        sealed=rows_by_ids(s,sorted(sealed_union(s)))
        v.artifact=artifact;v.evidence=evidence;v.sealed_mae=sealed_mae(artifact,sealed);v.sealed_rows=len(sealed)
        v.status='pending_approval';v.error=''
        event(s,'worker','候选训练完成',v.version_no,f'封样验收 MAE {v.sealed_mae}h，待负责人批准')
    except Exception as ex:
        v.status='failed';v.error=str(ex)[:600]
        event(s,'worker','候选训练失败',v.version_no,v.error)
def compare_on_sealed(s,candidate,active):
    """Live re-evaluation of both models on the same sealed batch at decision time."""
    sealed=rows_by_ids(s,sorted(sealed_union(s)))
    return sealed_mae(candidate.artifact,sealed),sealed_mae(active.artifact,sealed)
def approve(s,vid,epoch,u):
    g=locked_governance(s)
    if g.epoch!=epoch: raise HTTPException(409,'操作已过期：现役模型刚发生变更，请刷新后重试')
    v=item(s,ModelVersion,vid)
    if v.status!='pending_approval': raise HTTPException(409,'仅待批准的候选可上线')
    if sealed_union(s)&set(v.train_sample_ids): raise HTTPException(409,'封样范围已扩大并污染候选训练集，请重新训练候选')
    active=s.get(ModelVersion,g.active_version_id) if g.active_version_id else None
    cand_mae,active_mae=compare_on_sealed(s,v,active) if active else (sealed_mae(v.artifact,rows_by_ids(s,sorted(sealed_union(s)))),None)
    if active and cand_mae>active_mae+1e-9:
        reason=f'候选封样误差 {cand_mae}h 高于现役 {active_mae}h，不满足不劣于现役'
        event(s,u,'批准被拒绝',v.version_no,reason)
        s.commit()  # persist the rejection record independently; the switch itself never started
        raise HTTPException(409,reason)
    # Single-transaction switch: any failure rolls back and the old version stays live.
    if active: active.status='retired'
    v.status='active';v.sealed_mae=cand_mae;v.decided_by=u.email;v.decided_at=now()
    g.active_version_id=v.id;g.epoch+=1
    detail='首版单独验收上线' if not active else f'封样误差 {cand_mae}h ≤ 现役 {active_mae}h，替换 {active.version_no}'
    event(s,u,'批准上线',v.version_no,detail)
    return v
def reject(s,vid,reason,u):
    v=item(s,ModelVersion,vid)
    if v.status!='pending_approval': raise HTTPException(409,'仅待批准的候选可拒绝')
    v.status='rejected';v.rejection_reason=reason.strip();v.decided_by=u.email;v.decided_at=now()
    event(s,u,'拒绝候选',v.version_no,v.rejection_reason);return v
def rollback(s,vid,epoch,reason,u):
    g=locked_governance(s)
    if g.epoch!=epoch: raise HTTPException(409,'操作已过期：现役模型刚发生变更，请刷新后重试')
    v=item(s,ModelVersion,vid)
    if v.status!='retired': raise HTTPException(409,'仅已退役的历史版本可回退')
    active=s.get(ModelVersion,g.active_version_id) if g.active_version_id else None
    if not active: raise HTTPException(409,'当前无现役版本，回退无意义')
    active.status='retired';v.status='active';v.decided_by=u.email;v.decided_at=now()
    g.active_version_id=v.id;g.epoch+=1
    event(s,u,'回退版本',v.version_no,(reason.strip() or f'由 {active.version_no} 回退'))
    return v
def version_view(v):
    d=serialize(v);d.pop('artifact',None);d.pop('train_sample_ids',None)
    d['train_rows']=len(v.train_sample_ids)
    d['holdout_mae']=(v.evidence or {}).get('mae_hours')
    return d
def state_view(s):
    g=governance(s)
    active=s.get(ModelVersion,g.active_version_id) if g.active_version_id else None
    return {'epoch':g.epoch,'active_version_id':g.active_version_id,'active_version_no':active.version_no if active else None,
        'sealed_total':len(sealed_union(s)),'trainable_total':len(trainable_ids(s)),
        'batches':[serialize(b) for b in s.scalars(select(SealedBatch).order_by(SealedBatch.id.desc()))],
        'versions':[version_view(v) for v in s.scalars(select(ModelVersion).order_by(ModelVersion.id.desc()))],
        'events':[serialize(x) for x in s.scalars(select(GovernanceEvent).order_by(GovernanceEvent.id.desc()).limit(30))]}
