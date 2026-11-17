import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
STEEL={'P20':0,'H13':1,'S136':2}
FEATURES=['模腔','滑块','重量','钢材']
MIN_TRAIN_ROWS=30
def vector(x): return [x.cavities,x.slides,x.weight_kg,STEEL[x.steel]]
def fit_artifact(rows):
    """Train on the given rows only and return a JSON-serializable model artifact plus evidence."""
    if len(rows)<MIN_TRAIN_ROWS: raise ValueError(f'可用训练样本少于 {MIN_TRAIN_ROWS} 条，不能训练模型')
    x=np.array([vector(r) for r in rows]); y=np.array([r.actual_hours for r in rows])
    a,b,c,d=train_test_split(x,y,test_size=.2,random_state=42)
    pipe=make_pipeline(PolynomialFeatures(degree=2,interaction_only=True,include_bias=False),StandardScaler(),Ridge(alpha=3.0))
    pipe.fit(a,c)
    poly,scaler,ridge=pipe[0],pipe[1],pipe[2]
    artifact={'powers':poly.powers_.tolist(),'mean':[float(v) for v in scaler.mean_],'scale':[float(v) for v in scaler.scale_],'coef':[float(v) for v in ridge.coef_],'intercept':float(ridge.intercept_),'alpha':3.0,'seed':42}
    names=poly.get_feature_names_out(FEATURES)
    coeff=sorted(zip(names,ridge.coef_),key=lambda t:abs(t[1]),reverse=True)
    evidence={'mae_hours':round(float(mean_absolute_error(d,pipe.predict(b))),3),'training_rows':len(a),'holdout_rows':len(b),'seed':42,'alpha':3,'features':[{'name':n,'coefficient':round(float(v),3)} for n,v in coeff],'validation':[{'actual':round(float(t),2),'predicted':round(float(p),2)} for t,p in zip(d,pipe.predict(b))],'note':'系数来自标准化后的交叉特征，仅解释统计关系；预测包含本单准备工时。'}
    return artifact,evidence
def base_hours(artifact,vec):
    """Predict base trial hours (before setup) from a stored artifact; pure NumPy, no unpickling."""
    x=np.array(vec,dtype=float)
    z=np.array([float(np.prod(x**np.array(p))) for p in artifact['powers']])
    z=(z-np.array(artifact['mean']))/np.array(artifact['scale'])
    return float(np.dot(z,np.array(artifact['coef']))+artifact['intercept'])
def sealed_mae(artifact,rows):
    """Mean absolute error of base hours on the sealed acceptance samples."""
    if not rows: raise ValueError('封样批为空，无法计算验收误差')
    return round(float(np.mean([abs(r.actual_hours-base_hours(artifact,vector(r))) for r in rows])),3)
def predict_total(artifact,mould,setup):
    return round(max(.5,base_hours(artifact,vector(mould)))+setup,2)
