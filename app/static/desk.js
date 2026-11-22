import {draw} from './map.js';

const byId = id => document.getElementById(id);
const labels = {covered:'有效覆盖', pending:'待扫', unknown:'证据不足'};
const statuses = {ASSIGNED:'已派工', ACCEPTED:'已领取', DONE:'已完成', RETURNED:'已退回'};
const actions = {ASSIGNED:[['ACCEPTED','领取'],['RETURNED','退回']], ACCEPTED:[['DONE','完成'],['RETURNED','退回']], RETURNED:[['ACCEPTED','领取']], DONE:[]};
const headings = {routes:'线路册',tracks:'车辆轨迹',projection:'里程投影',windows:'清扫窗口',coverage:'覆盖合并',reconcile:'缺扫对账',dispatch:'接班派工',archive:'工单凭证'};
const state = {data:JSON.parse(byId('initial').textContent), lane:'', part:0, stage:'coverage', run:null, plan:null, planFor:'', jobs:[], busy:false};
const number = value => new Intl.NumberFormat('en-US').format(value);
const key = row => `${row.road}/${row.direction}`;
const direction = row => row.direction === '+' ? '顺向' : '逆向';
const escape = value => String(value ?? '—').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const cell = value => `<td>${escape(value)}</td>`;
const table = (headers, rows) => rows.length ? `<div class="scroll"><table><thead><tr>${headers.map(label=>`<th>${escape(label)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(cell).join('')}</tr>`).join('')}</tbody></table></div>` : '<p class="empty">暂无对应记录。</p>';
const names = {roads:'线路册',points:'车辆轨迹',windows:'作业窗口',coverage:'覆盖合并'};

function showMessage(message, error=false) {
  byId('message').textContent = message;
  byId('message').toggleAttribute('data-error', error);
}

function planView() {
  return state.plan ?? {...state.data.dispatch, tasks: state.data.dispatch.tasks.map(task => ({
    ...task, status:'ASSIGNED', status_label:statuses.ASSIGNED,
    handover:{status:'ASSIGNED', status_label:statuses.ASSIGNED, actor:null, note:null, updated_at:null},
  })), events:[]};
}

function metrics() {
  if (state.stage === 'dispatch') {
    const totals = planView().totals;
    return [['待扫差额',totals.pending_m],['已派工',totals.assigned_m],['未分配',totals.difference_after_m],['车辆',totals.vehicles],['转场里程',totals.transfer_m]];
  }
  const totals = state.data.reconcile.totals;
  return [['责任里程',totals.responsibility_m],['有效覆盖',totals.covered_m],['待扫',totals.pending_m],['证据不足',totals.unknown_m],['重复扣除',totals.duplicate_m]];
}

function dispatchView() {
  const plan = planView();
  const totals = plan.totals;
  const published = Boolean(state.plan);
  let detail = `<p class="lead">交接批次 ${escape(plan.batch)} · 待扫差额 ${number(totals.pending_m)} m · 已派 ${number(plan.tasks.length)} 辆 · 未分配 ${number(totals.difference_after_m)} m</p>`;
  detail += published
    ? '<p class="hint">清单已冻结，每辆车按顺序领取区间；状态实时回写。</p>'
    : '<p class="hint">清单尚未发布。核量后发布，车辆即可领取。</p><div class="row-actions"><button data-publish>发布派工清单</button></div>';
  for (const task of plan.tasks) {
    const lifecycle = task.status || 'ASSIGNED';
    const canMove = actions[lifecycle] ?? [];
    detail += `<article class="task" data-task="${escape(task.task_id)}">
      <header><strong>${escape(task.vehicle)}</strong><span class="tag ${lifecycle.toLowerCase()}">${escape(statuses[lifecycle])}</span>
        <span class="num">${number(task.responsibility_m)} m · ${task.stops.length} 段 · 转场 ${number(task.transfer_m)} m</span></header>
      ${table(['序','道路','方向','区间','里程','转场','依据'], task.stops.map(stop => [
        stop.seq, `${stop.road} ${stop.name}`, direction(stop), `${stop.from_m}–${stop.to_m} m`, `${stop.m} m`,
        `${stop.transfer_m} m`, `覆盖合并 · ${stop.direction}向 · 第${stop.part_index + 1}段 · 待扫`,
      ]))}
      ${published ? `<form class="handover-form" data-task="${escape(task.task_id)}">
        <label>交接人 <input name="actor" required maxlength="100" value="${escape(task.handover?.actor ?? '')}"></label>
        <label>备注 <input name="note" maxlength="200" value="${escape(task.handover?.note ?? '')}"></label>
        ${canMove.map(([value,label]) => `<button data-status="${value}">${label}</button>`).join('') || '<span class="hint">已完成交接</span>'}
        <span class="hint">${escape(task.handover?.updated_at ?? '尚未交接')}</span>
      </form>` : ''}
    </article>`;
  }
  if (plan.events?.length) {
    detail += '<h3>交接日志</h3>' + table(['任务','状态','交接人','备注','时间'], plan.events.map(event => [
      plan.tasks.find(task => task.task_id === event.task_id)?.vehicle ?? event.task_id.slice(0, 8),
      statuses[event.status] ?? event.status, event.actor, event.note || '—', event.at,
    ]));
  }
  if (plan.held?.length) {
    detail += '<h3>不派工区间</h3>' + table(['道路','方向','区间','里程','原因'], plan.held.map(item => [
      `${item.road}`, direction(item), `${item.from_m}–${item.to_m} m`, `${item.m} m`, '证据不足，需复核',
    ]));
  }
  return detail;
}

function render() {
  const {data,stage} = state;
  byId('metrics').innerHTML = metrics().map(([title,value]) => `<div class="metric"><span>${title}</span><strong>${number(value)} <small>m</small></strong></div>`).join('');
  const rows = data.coverage.rows;
  const current = rows.find(row => key(row) === state.lane) || rows[0];
  state.lane = current ? key(current) : '';
  const options = rows.map(row => new Option(`${row.road} · ${row.name} ${direction(row)}`, key(row)));
  byId('lane').replaceChildren(...options); byId('lane').value = state.lane;
  byId('lane').disabled = !current;
  byId('stage-title').textContent = headings[stage];
  byId('route-label').textContent = current ? `${current.name} · ${direction(current)}` : '无有效线路';
  byId('scale').replaceChildren(...(current?.parts ?? []).map((part,index) => {
    const button = document.createElement('button'); button.type = 'button'; button.className = part.kind;
    button.style.flex = `${part.m} 0 0px`; button.dataset.part = index;
    button.setAttribute('aria-label', `${part.from_m}–${part.to_m} 米 · ${labels[part.kind]}`);
    return button;
  }));
  byId('ticks').innerHTML = current ? [current.from_m, Math.floor((current.from_m+current.to_m)/2),current.to_m].map(value=>`<span>${value} m</span>`).join('') : '';
  const plan = stage === 'dispatch' ? planView() : null;
  state.jobs = plan ? plan.tasks.flatMap(task => task.stops.map(stop => ({...stop, task_id:task.task_id, vehicle:task.vehicle}))) : [];
  draw(byId('map'), rows, state.lane, state.jobs);
  const selected = section => (data[section]?.rows ?? []).filter(row => key(row) === state.lane);
  const problems = stage === 'reconcile' || stage === 'coverage' || stage === 'archive' ? data.reconcile.issues
    : stage === 'dispatch' ? data.dispatch.issues : data[stage].issues;
  byId('records-count').textContent = `${problems.length} 条`;
  byId('issues').innerHTML = table(['来源','行号','原因码','判定'], problems.map(row => [names[row.table] ?? row.table, row.end_line ? `${row.line}–${row.end_line}` : row.line,row.code,row.detail]));
  byId('balance').textContent = stage === 'dispatch'
    ? (plan.totals.difference_after_m === 0 ? '待扫差额已全部派工' : `尚有 ${plan.totals.difference_after_m} m 未派工`)
    : data.reconcile.status === 'MATCHED' ? '责任里程已对平' : '责任里程待复核';
  byId('batch').textContent = `${data.batch} · ${data.at} · ${data.ruleset}`;
  let detail = '';
  if (stage === 'archive') detail = archiveView();
  else if (stage === 'dispatch') detail = dispatchView();
  else if (current && stage === 'coverage') {
    const part = current.parts[state.part] ?? current.parts[0];
    detail = current.parts.map((item,index) => `<button class="span-choice" data-part="${index}" aria-pressed="${item === part}"><span>${item.from_m}–${item.to_m} m</span><span class="tag ${item.kind}">${labels[item.kind]}</span><strong class="num">${item.m} m</strong></button>`).join('');
    detail += '<h3>区间证据</h3>' + table(['车辆','轨迹行','窗口行'],part.references.map(row=>[row.vehicle,`${row.line}–${row.end_line}`,row.window_lines.join('、')]));
  } else if (stage === 'routes') detail = table(['道路','方向','责任区间'],selected(stage).map(row=>[row.road,direction(row),`${row.from_m}–${row.to_m} m`]));
  else if (stage === 'tracks') detail = table(['轨迹行','车辆','时间','铲位'],selected(stage).map(row=>[row.line,row.vehicle,row.raw.time,row.plow?'启用':'关闭']));
  else if (stage === 'projection') detail = table(['轨迹行','车辆','桩距','偏移'],selected(stage).map(row=>[row.line,row.vehicle,row.m === null ? '—' : `${row.m} m`,row.offset_m === null ? '—' : `${row.offset_m} m`]));
  else if (stage === 'windows') detail = table(['轨迹行','起点','终点','判定'],selected(stage).map(row=>[`${row.line}–${row.end_line}`,`${row.from_m} m`,`${row.to_m} m`,labels[row.kind]]));
  else if (stage === 'reconcile') detail = table(['责任','有效','待扫','缺证'],selected(stage).map(row=>[row.responsibility_m,row.covered_m,row.pending_m,row.unknown_m].map(value=>`${value} m`)));
  byId('stage-detail').innerHTML = detail || '<p class="empty">选择有效线路。</p>';
  byId('stage-detail').classList.toggle('dispatch', stage === 'dispatch');
  document.querySelectorAll('nav a').forEach(link => {
    if (link.dataset.stage === stage) link.setAttribute('aria-current','page');
    else link.removeAttribute('aria-current');
  });
}

function archiveView() {
  if (!state.run) return '<p class="empty">运行核量后查看凭证。</p><button data-history>查找历史</button><div id="history"></div>';
  const {id,manifest,signature} = state.run;
  return `<p>${escape(manifest.batch)} · ${escape(manifest.generated_at)}</p><code class="digest">${escape(manifest.digest)}</code>
  <div class="row-actions"><button data-rerun>重跑核量</button><a class="download" href="/api/runs/${encodeURIComponent(id)}/export">导出凭证</a><button data-history>查找历史</button></div>
  ${signature ? `<p>已签收 · ${escape(signature.reviewer)}</p>` : '<form class="archive-form" id="sign"><label>签收人 <input name="reviewer" required maxlength="100"></label><button>签收</button></form>'}<div id="history"></div>`;
}

async function request(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const body = await response.json();
  if (!response.ok) throw new Error(body.message || '请求失败，请重试。');
  return body;
}
async function action(operation) {
  if (state.busy) return;
  state.busy = true; showMessage('正在处理…');
  try {await operation();} catch (error) {showMessage(error.message,true);} finally {state.busy = false;}
}
function accept(run) {
  state.run = run; state.data = run.result;
  state.plan = null; state.planFor = '';
  render();
}
async function loadPlan() {
  if (state.planFor === state.data.batch) return;
  try { state.plan = await request(`/api/dispatch/plans/${encodeURIComponent(state.data.batch)}`); }
  catch { state.plan = null; }
  state.planFor = state.data.batch;
}
function switchStage() {
  const stage = location.hash.slice(1); state.stage = headings[stage] ? stage : 'coverage';
  render();
  if (state.stage === 'dispatch') action(async () => { await loadPlan(); render(); });
}
window.addEventListener('hashchange',switchStage);
byId('lane').addEventListener('change',event=>{state.lane=event.target.value; state.part=0; render();});
byId('sample').addEventListener('change',event=>{location.href=`/?sample=${event.target.value}${location.hash}`;});
byId('toolbar').addEventListener('submit',event=>{event.preventDefault(); action(async()=>{
  const run = state.run ? await request(`/api/runs/${state.run.id}/rerun`,{}) : await request('/api/runs',{sample:byId('sample').value});
  const plan = run.plan ?? await request(`/api/dispatch/plans/${encodeURIComponent(run.result?.batch ?? run.manifest.batch)}`).catch(()=>null);
  accept(run); state.plan = plan; state.planFor = plan ? state.data.batch : '';
  render(); showMessage(run.reused ? '重跑一致' : '核量已归档');
});});
byId('import').addEventListener('click',()=>byId('file').click());
byId('file').addEventListener('change',event=>{
  const [file] = event.target.files; if (!file) return;
  action(async()=>{let source;try{source=JSON.parse(await file.text());}catch{throw new Error('无法读取批次 JSON，请检查文件。');}
    accept(await request('/api/runs',{source})); await loadPlan(); render(); showMessage('导入已归档');
  }).finally(()=>{event.target.value='';});
});
byId('scale').addEventListener('click',event=>{if(event.target.dataset.part===undefined)return; state.part=Number(event.target.dataset.part); location.hash='coverage'; render();});
byId('stage-detail').addEventListener('click',event=>{
  const button=event.target.closest('button'); if(!button)return;
  if(button.dataset.part!==undefined){state.part=Number(button.dataset.part);render();return;}
  if (button.hasAttribute('data-publish')){action(async()=>{
    const published = state.run
      ? await request(`/api/runs/${state.run.id}/dispatch`,{})
      : await request('/api/runs',{sample:byId('sample').value});
    if (!state.run) accept(published);
    state.plan = published.plan ?? await request(`/api/dispatch/plans/${encodeURIComponent(state.data.batch)}`);
    state.planFor = state.data.batch; render(); showMessage('派工清单已发布');
  }); return;}
  if (!button.matches('[data-rerun],[data-history],[data-run]')) return;
  action(async()=>{
    if(button.hasAttribute('data-rerun')){const run=await request(`/api/runs/${state.run.id}/rerun`,{});accept(run);await loadPlan();render();showMessage('重跑一致');}
    if(button.hasAttribute('data-history')){
      const {runs}=await request('/api/runs');
      byId('history').replaceChildren(...runs.map(run=>{const item=document.createElement('button');item.dataset.run=run.id;item.textContent=run.batch;return item;}));
      showMessage(runs.length?`${runs.length} 笔运行`:'暂无归档');
    }
    if(button.dataset.run){const run=await request(`/api/runs/${button.dataset.run}`);state.run=run;state.data=run.result;state.plan=null;render();showMessage('已打开凭证');}
  });
});
byId('stage-detail').addEventListener('submit',event=>{
  event.preventDefault();
  if(event.target.id==='sign'){
    action(async()=>{const receipt=await request(`/api/runs/${state.run.id}/sign`,{reviewer:new FormData(event.target).get('reviewer'),digest:state.run.manifest.digest});state.run.signature=receipt;render();showMessage('凭证已签收');});
    return;
  }
  const form=event.target.closest('.handover-form'); if(!form) return;
  const status=event.submitter?.dataset.status; if(!status) return;
  const data=new FormData(form);
  action(async()=>{
    state.plan=await request(`/api/dispatch/plans/${encodeURIComponent(state.data.batch)}/handover`,{
      task_id:form.dataset.task,status,actor:data.get('actor'),note:data.get('note')??''});
    render(); showMessage(state.plan.receipt?.reused?'交接状态已存在':'交接已记录');
  });
});
new ResizeObserver(()=>draw(byId('map'),state.data.coverage.rows,state.lane,state.jobs ?? [])).observe(byId('map'));
switchStage();
