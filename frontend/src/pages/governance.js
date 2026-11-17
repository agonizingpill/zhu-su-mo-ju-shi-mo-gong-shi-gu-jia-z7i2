import {esc,number,money} from '../utils/format.js';
import {send} from '../api.js';
import {notify,badge,empty} from '../components/common.js';
import {VERSION_STATES} from '../constants.js';
const vb=v=>`<span class="status ${esc(v.status)}">${esc(VERSION_STATES[v.status]||v.status)}</span>`;
const stamp=x=>esc((x||'').replace('T',' ').slice(0,19));
function actions(s,v){
  const admin=s.user.role==='admin',writer=s.user.role!=='viewer';
  if(v.status==='pending_approval')return `<button class="small" data-approve="${v.id}" ${admin?'':'disabled'}>批准上线</button> <input style="width:130px;display:inline-block;padding:5px" placeholder="拒绝原因" id="reject-reason-${v.id}" ${admin?'':'disabled'}> <button class="small" data-reject="${v.id}" ${admin?'':'disabled'}>拒绝</button>`;
  if(v.status==='training'||v.status==='failed')return `<button class="small" data-retry="${v.id}" ${writer?'':'disabled'}>重试训练</button>${v.error?`<br><small>${esc(v.error)}</small>`:''}`;
  if(v.status==='retired')return `<button class="small" data-rollback="${v.id}" ${admin?'':'disabled'}>回退到此版</button>`;
  if(v.status==='rejected')return `<small>拒绝原因：${esc(v.rejection_reason)}</small>`;
  return '<small>现役报价模型</small>';
}
export function render(s){
  const g=s.governance||{versions:[],batches:[],events:[]},active=g.versions.find(v=>v.status==='active');
  const unsealed=s.trials.filter(t=>!t.sealed);
  return `<div class="heading"><div><div class="kicker">10 / MODEL GOVERNANCE</div><h1>模型验收与版本治理</h1><p class="muted">封样样本永不参与训练；候选须在封样批上不劣于现役才可批准。</p></div></div>
<div class="ribbon"><div>现役版本<strong class="mono">${esc(g.active_version_no||'无')}</strong></div><div>现役封样 MAE<strong class="mono">${active?number(active.sealed_mae)+' h':'—'}</strong></div><div>治理纪元<strong class="mono">${g.epoch??0}</strong></div><div>可训练样本<strong class="mono">${g.trainable_total??0} 条</strong></div><div>已封存样本<strong class="mono">${g.sealed_total??0} 条</strong></div></div>
${active?'':empty('当前无现役模型版本，试模估价已阻断。请负责人封存试模样本、训练候选并完成首版验收。')}
<div class="split"><section class="panel"><h2>候选与版本</h2><div class="actions"><button id="new-candidate" class="primary" ${s.user.role==='viewer'?'disabled':''}>训练新候选</button></div><p class="note">候选训练自动排除全部封样；验收期间报价仍使用现役模型。批准后新旧版本原子切换，失败保留旧版。</p><div class="tablewrap"><table><thead><tr><th>版本</th><th>状态</th><th>训练样本</th><th>留出 MAE</th><th>封样 MAE</th><th>创建</th><th>操作</th></tr></thead><tbody>${g.versions.map(v=>`<tr><td><b class="mono">${esc(v.version_no)}</b></td><td>${vb(v)}</td><td class="mono">${v.train_rows} 条</td><td class="mono">${number(v.holdout_mae)} h</td><td class="mono">${number(v.sealed_mae)} h</td><td><small>${esc(v.created_by)}<br>${stamp(v.stamp)}</small></td><td>${actions(s,v)}</td></tr>`).join('')||'<tr><td colspan="7">尚无模型版本。</td></tr>'}</tbody></table></div>
<h3 style="margin-top:30px">估单版本台账</h3><div class="tablewrap"><table><thead><tr><th>估单</th><th>状态</th><th>模型版本</th><th>预测工时</th><th>报价</th></tr></thead><tbody>${s.estimates.map(e=>`<tr><td><b>${esc(e.code)}</b></td><td>${badge(e)}</td><td class="mono">${esc(e.model_version||'—')}</td><td class="mono">${number(e.predicted_hours)} h</td><td class="mono">${money(e.quote_amount)}</td></tr>`).join('')}</tbody></table></div><p class="note">在途估价沿用入队时锁定的版本；历史估单保留原结果，不因版本切换重算。</p></section>
<aside class="panel paper"><h2>封样管理</h2>${g.batches.length?`<table><thead><tr><th>封样批</th><th>样本数</th><th>校验</th></tr></thead><tbody>${g.batches.map(b=>`<tr><td><b>${esc(b.name)}</b><br><small>${esc(b.created_by)} · ${stamp(b.stamp)}</small></td><td class="mono">${b.sample_count}</td><td class="mono"><small>${esc(b.sample_hash.slice(0,10))}</small></td></tr>`).join('')}</tbody></table>`:'<p class="note">尚未封存验收样本。</p>'}<form id="seal-form"><label>新封样批名称</label><input name="name" value="SEAL-${Date.now().toString().slice(-6)}" required><label>从未封样本中勾选（至少 8 条，且封存后训练样本不得少于 30 条）</label><div style="max-height:240px;overflow:auto;border:1px solid var(--line);padding:8px">${unsealed.map(t=>`<label style="display:inline-block;width:31%;margin:2px 0;font-size:11px"><input type="checkbox" name="trial_ids" value="${t.id}" style="width:auto"> ${esc(t.trial_code)}</label>`).join('')||'<small>全部试模样本均已封存。</small>'}</div><div class="actions"><button type="button" class="small" id="seal-all">全选未封</button><button class="primary" ${s.user.role==='admin'?'':'disabled'}>封存样本</button></div></form><p class="note">封存后该批样本从所有训练（含候选与重试）中永久排除，仅用于验收比较基础工时误差。</p></aside></div>
<section class="panel" style="margin-top:30px"><h2>治理事件与拒绝原因</h2><div class="tablewrap"><table><thead><tr><th>时间</th><th>操作人</th><th>事件</th><th>版本</th><th>说明 / 拒绝原因</th></tr></thead><tbody>${g.events.map(x=>`<tr><td class="mono"><small>${stamp(x.stamp)}</small></td><td>${esc(x.actor)}</td><td>${esc(x.action)}</td><td class="mono">${esc(x.version_no||'—')}</td><td><small>${esc(x.detail)}</small></td></tr>`).join('')||'<tr><td colspan="5">暂无治理事件。</td></tr>'}</tbody></table></div></section>`}
export function bind(s,reload){
  const g=s.governance||{epoch:0};
  const q=s=>document.querySelector(s);
  q('#new-candidate').onclick=async()=>{try{await send('/governance/candidates');notify('候选已入队训练，固定当前非封样样本');await reload()}catch(x){notify(x.message)}};
  document.querySelectorAll('[data-retry]').forEach(b=>b.onclick=async()=>{try{await send(`/governance/candidates/${b.dataset.retry}/retry`);notify('已按原固定样本重试，未新建候选');await reload()}catch(x){notify(x.message)}});
  document.querySelectorAll('[data-approve]').forEach(b=>b.onclick=async()=>{try{await send(`/governance/versions/${b.dataset.approve}/approve`,{epoch:g.epoch});notify('候选已批准上线，现役版本已切换');await reload()}catch(x){notify(x.message);await reload()}});
  document.querySelectorAll('[data-reject]').forEach(b=>b.onclick=async()=>{const reason=q(`#reject-reason-${b.dataset.reject}`).value.trim();try{await send(`/governance/versions/${b.dataset.reject}/reject`,{reason});notify('候选已拒绝并记录原因');await reload()}catch(x){notify(x.message)}});
  document.querySelectorAll('[data-rollback]').forEach(b=>b.onclick=async()=>{try{await send(`/governance/versions/${b.dataset.rollback}/rollback`,{epoch:g.epoch,reason:''});notify('已回退到历史版本');await reload()}catch(x){notify(x.message);await reload()}});
  const all=q('#seal-all');if(all)all.onclick=()=>{document.querySelectorAll('input[name=trial_ids]').forEach(c=>c.checked=true)};
  q('#seal-form').onsubmit=async ev=>{ev.preventDefault();const name=new FormData(ev.target).get('name');const trial_ids=[...ev.target.querySelectorAll('input[name=trial_ids]:checked')].map(c=>Number(c.value));try{await send('/governance/seal',{name,trial_ids});notify('封样批已封存，历次训练将排除');await reload()}catch(x){notify(x.message)}};
}
