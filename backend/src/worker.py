import os,json,logging
from pathlib import Path
import redis
from sqlalchemy import select
from .db import Session
from .models import Estimate,Mould
from .governance_models import EstimateModelPin,ModelVersion
from .ml import predict_total
from .governance_service import train_version
r=redis.Redis.from_url(os.environ['REDIS_URL'],decode_responses=True)
ARTIFACTS=os.getenv('ARTIFACTS_DIR','/artifacts')
Path(ARTIFACTS).mkdir(exist_ok=True)
def estimate_job(eid):
    with Session() as s:
        e=s.get(Estimate,eid)
        if not e or e.status!='calculating':return
        try:
            pin=s.scalar(select(EstimateModelPin).where(EstimateModelPin.estimate_id==eid))
            if not pin: raise ValueError('估单未锁定模型版本，请重新发起估算')
            v=s.get(ModelVersion,pin.version_id)
            if not v or not v.artifact: raise ValueError(f'模型版本 {pin.version_no} 缺少推理产物')
            e.predicted_hours=predict_total(v.artifact,s.get(Mould,e.mould_id),e.setup_hours)
            e.model_result={**v.evidence,'model_version':v.version_no,'sealed_mae_hours':v.sealed_mae,'note':v.evidence['note']+f"本单由入队时锁定的 {v.version_no} 推理，该版本封样验收 MAE {v.sealed_mae}h。"}
            e.status='estimated'
            Path(f'{ARTIFACTS}/estimate-{eid}.json').write_text(json.dumps(e.model_result,ensure_ascii=False))
        except Exception as ex:
            logging.exception('estimate failed');e.status='failed';e.model_result={'error':str(ex)}
        s.commit()
def training_job(vid):
    with Session() as s:
        train_version(s,vid)
        s.commit()
def main():
    while True:
        Path('/tmp/worker-heartbeat').touch()
        entry=r.blpop(['model-training','mould-estimates'],timeout=2)
        if not entry: continue
        queue,key=entry
        if queue=='model-training': training_job(int(key))
        else: estimate_job(int(key))
if __name__=='__main__': main()
