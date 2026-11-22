import {draw} from './map.js';

const byId = id => document.getElementById(id);
const labels = {covered:'有效覆盖', pending:'待扫', unknown:'证据不足'};
const headings = {routes:'线路册',tracks:'车辆轨迹',projection:'里程投影',windows:'清扫窗口',coverage:'覆盖合并',reconcile:'缺扫对账',archive:'工单凭证'};
const state = {data:JSON.parse(byId('initial').textContent), lane:'', part:0, stage:'coverage', run:null, busy:false};
const number = value => new Intl.NumberFormat('en-US').format(value);
const key = row => `${row.road}/${row.direction}`;
const direction = row => row.direction === '+' ? '顺向' : '逆向';
const escape = value => String(value ?? '—').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const cell = value => `<td>${escape(value)}</td>`;
const table = (headers, rows) => rows.length ? `<div class="scroll"><table><thead><tr>${headers.map(label=>`<th>${escape(label)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(cell).join('')}</tr>`).join('')}</tbody></table></div>` : '<p class="empty">暂无对应记录。</p>';
const names = {roads:'线路册',points:'车辆轨迹',windows:'作业窗口'};

function showMessage(message, error=false) {
  byId('message').textContent = message;
  byId('message').toggleAttribute('data-error', error);
}

function render() {
  const {data,stage} = state;
  const totals = data.reconcile.totals;
  byId('metrics').innerHTML = [['责任里程',totals.responsibility_m],['有效覆盖',totals.covered_m],['待扫',totals.pending_m],['证据不足',totals.unknown_m],['重复扣除',totals.duplicate_m]].map(([title,value]) => `<div class="metric"><span>${title}</span><strong>${number(value)} <small>m</small></strong></div>`).join('');
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
  draw(byId('map'), rows, state.lane);
  const selected = section => (data[section]?.rows ?? []).filter(row => key(row) === state.lane);
  const problems = stage === 'reconcile' || stage === 'coverage' || stage === 'archive' ? data.reconcile.issues : data[stage].issues;
  byId('records-count').textContent = `${problems.length} 条`;
  byId('issues').innerHTML = table(['来源','行号','原因码','判定'], problems.map(row => [names[row.table] ?? row.table, row.end_line ? `${row.line}–${row.end_line}` : row.line,row.code,row.detail]));
  byId('balance').textContent = data.reconcile.status === 'MATCHED' ? '责任里程已对平' : '责任里程待复核';
  byId('batch').textContent = `${data.batch} · ${data.at} · ${data.ruleset}`;
  let detail = '';
  if (stage === 'archive') detail = archiveView();
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
function accept(run) {state.run = run; state.data = run.result; render();}
function switchStage() {const stage = location.hash.slice(1); state.stage = headings[stage] ? stage : 'coverage'; render();}
window.addEventListener('hashchange',switchStage);
byId('lane').addEventListener('change',event=>{state.lane=event.target.value; state.part=0; render();});
byId('sample').addEventListener('change',event=>{location.href=`/?sample=${event.target.value}${location.hash}`;});
byId('toolbar').addEventListener('submit',event=>{event.preventDefault(); action(async()=>{
  const run = state.run ? await request(`/api/runs/${state.run.id}/rerun`,{}) : await request('/api/runs',{sample:byId('sample').value});
  accept(run); showMessage(run.reused?'重跑一致':'核量已归档');
});});
byId('import').addEventListener('click',()=>byId('file').click());
byId('file').addEventListener('change',event=>{
  const [file] = event.target.files; if (!file) return;
  action(async()=>{let source;try{source=JSON.parse(await file.text());}catch{throw new Error('无法读取批次 JSON，请检查文件。');}
    accept(await request('/api/runs',{source})); showMessage('导入已归档');
  }).finally(()=>{event.target.value='';});
});
byId('scale').addEventListener('click',event=>{if(event.target.dataset.part===undefined)return; state.part=Number(event.target.dataset.part); location.hash='coverage'; render();});
byId('stage-detail').addEventListener('click',event=>{
  const button=event.target.closest('button'); if(!button)return;
  if(button.dataset.part!==undefined){state.part=Number(button.dataset.part);render();return;}
  if (!button.matches('[data-rerun],[data-history],[data-run]')) return;
  action(async()=>{
    if(button.hasAttribute('data-rerun')){accept(await request(`/api/runs/${state.run.id}/rerun`,{}));showMessage('重跑一致');}
    if(button.hasAttribute('data-history')){
      const {runs}=await request('/api/runs');
      byId('history').replaceChildren(...runs.map(run=>{const item=document.createElement('button');item.dataset.run=run.id;item.textContent=run.batch;return item;}));
      showMessage(runs.length?`${runs.length} 笔运行`:'暂无归档');
    }
    if(button.dataset.run){accept(await request(`/api/runs/${button.dataset.run}`));showMessage('已打开凭证');}
  });
});
byId('stage-detail').addEventListener('submit',event=>{
  if(event.target.id!=='sign')return; event.preventDefault();
  action(async()=>{const receipt=await request(`/api/runs/${state.run.id}/sign`,{reviewer:new FormData(event.target).get('reviewer'),digest:state.run.manifest.digest});state.run.signature=receipt;render();showMessage('凭证已签收');});
});
new ResizeObserver(()=>draw(byId('map'),state.data.coverage.rows,state.lane)).observe(byId('map'));
switchStage();
