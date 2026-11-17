import os
import redis
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from .db import db_session
from .auth import current,writers,admin
from .models import TrialHistory
from .governance_models import SealedBatch
from .governance_schemas import SealInput,EpochInput,RejectInput,RollbackInput
from .services import serialize
from . import governance_service as svc
router=APIRouter()
r=redis.Redis.from_url(os.environ['REDIS_URL'],decode_responses=True)
def enqueue(s,v):
    try: r.rpush('model-training',v.id)
    except Exception:
        v.status='failed';v.error='训练队列暂不可用';s.commit()
        raise HTTPException(503,'训练队列暂不可用，请重试')
@router.get('/governance')
def state(s=Depends(db_session),u=Depends(current)):
    v=svc.state_view(s);s.commit();return v
@router.get('/governance/trials')
def trials(s=Depends(db_session),u=Depends(current)):
    blocked=svc.sealed_union(s)
    return [{'id':x.id,'trial_code':x.trial_code,'cavities':x.cavities,'slides':x.slides,'steel':x.steel,'weight_kg':x.weight_kg,'actual_hours':x.actual_hours,'sealed':x.id in blocked} for x in s.scalars(select(TrialHistory).order_by(TrialHistory.id))]
@router.post('/governance/seal')
def seal(p:SealInput,s=Depends(db_session),u=Depends(admin)):
    b=svc.seal_batch(s,p,u);s.commit();return serialize(b)
@router.post('/governance/candidates')
def create(s=Depends(db_session),u=Depends(writers)):
    v=svc.create_candidate(s,u);s.commit();enqueue(s,v);return svc.version_view(v)
@router.post('/governance/candidates/{vid}/retry')
def retry(vid:int,s=Depends(db_session),u=Depends(writers)):
    v=svc.retry_candidate(s,vid,u);s.commit();enqueue(s,v);return svc.version_view(v)
@router.post('/governance/versions/{vid}/approve')
def approve(vid:int,p:EpochInput,s=Depends(db_session),u=Depends(admin)):
    v=svc.approve(s,vid,p.epoch,u);s.commit();return svc.version_view(v)
@router.post('/governance/versions/{vid}/reject')
def reject(vid:int,p:RejectInput,s=Depends(db_session),u=Depends(admin)):
    v=svc.reject(s,vid,p.reason,u);s.commit();return svc.version_view(v)
@router.post('/governance/versions/{vid}/rollback')
def rollback(vid:int,p:RollbackInput,s=Depends(db_session),u=Depends(admin)):
    v=svc.rollback(s,vid,p.epoch,p.reason,u);s.commit();return svc.version_view(v)
