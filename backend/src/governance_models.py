"""Model governance: sealed acceptance samples, versioned candidates and the live-model switchboard."""
from sqlalchemy import String,Float,Integer,ForeignKey,JSON
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
class SealedBatch(Base):
    """A batch of trial-history samples sealed by the owner; excluded from every training run forever."""
    __tablename__='sealed_batches'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(60),unique=True)
    sample_ids:Mapped[list]=mapped_column(JSON)
    sample_count:Mapped[int]=mapped_column(Integer)
    sample_hash:Mapped[str]=mapped_column(String(64))
    created_by:Mapped[str]=mapped_column(String(120))
    stamp:Mapped[str]=mapped_column(String(40))
class ModelVersion(Base):
    __tablename__='model_versions'
    id:Mapped[int]=mapped_column(primary_key=True)
    version_no:Mapped[str]=mapped_column(String(20),unique=True)
    status:Mapped[str]=mapped_column(String(20),default='training')
    train_sample_ids:Mapped[list]=mapped_column(JSON)
    train_hash:Mapped[str]=mapped_column(String(64))
    artifact:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    evidence:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    sealed_mae:Mapped[float|None]=mapped_column(Float,nullable=True)
    sealed_rows:Mapped[int]=mapped_column(Integer,default=0)
    error:Mapped[str]=mapped_column(String(600),default='')
    rejection_reason:Mapped[str]=mapped_column(String(600),default='')
    created_by:Mapped[str]=mapped_column(String(120))
    stamp:Mapped[str]=mapped_column(String(40))
    decided_by:Mapped[str|None]=mapped_column(String(120),nullable=True)
    decided_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
class GovernanceState(Base):
    """Singleton row (id=1): optimistic-concurrency epoch plus the live-version pointer."""
    __tablename__='governance_state'
    id:Mapped[int]=mapped_column(primary_key=True)
    epoch:Mapped[int]=mapped_column(Integer,default=0)
    active_version_id:Mapped[int|None]=mapped_column(ForeignKey('model_versions.id'),nullable=True)
class GovernanceEvent(Base):
    __tablename__='governance_events'
    id:Mapped[int]=mapped_column(primary_key=True)
    actor:Mapped[str]=mapped_column(String(120))
    action:Mapped[str]=mapped_column(String(40))
    version_no:Mapped[str]=mapped_column(String(20),default='')
    detail:Mapped[str]=mapped_column(String(600),default='')
    stamp:Mapped[str]=mapped_column(String(40))
class EstimateModelPin(Base):
    """Model version pinned to an estimate at enqueue time; in-flight estimates never switch models."""
    __tablename__='estimate_model_pins'
    id:Mapped[int]=mapped_column(primary_key=True)
    estimate_id:Mapped[int]=mapped_column(ForeignKey('estimates.id'),unique=True)
    version_id:Mapped[int]=mapped_column(ForeignKey('model_versions.id'))
    version_no:Mapped[str]=mapped_column(String(20))
    pinned_at:Mapped[str]=mapped_column(String(40))
